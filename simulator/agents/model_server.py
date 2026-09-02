# -*- coding: utf-8 -*-
"""
에이전트용 모델 서버 — GPU 서버에 모델만 올리고 브라우저는 노트북에서 돌린다
================================================================================

왜 서버로 떼는가
    `--local-model` 은 러너 프로세스 안에 모델을 올린다. 워커마다 한 벌씩
    올라가서 노트북 8GB 로는 3B 한 개가 한계였고, 그 3B 는 "이미 본 상품이므로"
    라고 써놓고 그 상품을 누르는 식으로 상태 추적을 자주 놓쳤다.

    배정된 GPU 서버(V100S 32GB)에는 주피터만 있고 node 도 sudo 도 없어서
    프론트와 Playwright 를 올릴 수 없다. 그래서 **모델만** 서버에 두고
    브라우저는 노트북에 남긴다. 7B 이상을 쓸 수 있고 노트북 GPU 가 비어
    워커도 늘어난다.

무엇을 하는가
    OpenAI 의 chat completions 를 흉내 낸 최소 서버다. 러너의 `ask()` 가
    보내는 것만 받는다 — model / messages / max_tokens / temperature.
    `response_format` 같은 모르는 필드는 조용히 무시한다.

    작은 모델이 서두를 붙이는 버릇이 있어 `{"action": "` 를 프롬프트 끝에
    미리 넣고, 응답 앞에 그대로 되붙여 돌려준다. LocalLLM 과 같은 수법이다.

    GPU 한 장이라 생성은 락으로 직렬화한다. 워커가 여러 개여도 순서대로 처리된다.

실행 (GPU 서버 주피터 터미널)
    pip install --user transformers accelerate     # 이미 있으면 생략
    python simulator/agents/model_server.py --model Qwen/Qwen2.5-7B-Instruct --port 8501

사용 (노트북)
    python simulator/agents/agent_runner.py --limit 10 \
        --api-base http://70.12.130.103:8501/v1 --model Qwen/Qwen2.5-7B-Instruct

주의
    인증이 없다. 사내망에서만 띄우고, 끝나면 내린다.
    V100 은 bfloat16 이 없다. float16 으로 고정한다 — bf16 을 주면 느려지거나 죽는다.
"""
import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL = None
TOK = None
LOCK = threading.Lock()          # GPU 한 장. 생성은 한 번에 하나만
ARGS = None
PREFILL = '{"action": "'


def generate(messages, max_tokens, temperature):
    import torch
    prompt = TOK.apply_chat_template(messages, tokenize=False,
                                     add_generation_prompt=True)
    prompt += PREFILL
    ids = TOK(prompt, return_tensors="pt").to(MODEL.device)
    with LOCK, torch.no_grad():
        out = MODEL.generate(**ids, max_new_tokens=max_tokens,
                             do_sample=temperature > 0, temperature=temperature or 1.0,
                             top_p=0.9, pad_token_id=TOK.eos_token_id)
    new = out[0][ids["input_ids"].shape[1]:]
    text = TOK.decode(new, skip_special_tokens=True)
    # 길이로 잘렸는지 알려 준다. 러너가 finish_reason 을 본다
    finish = "length" if len(new) >= max_tokens else "stop"
    return PREFILL + text, finish


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            self._send(200, {"object": "list",
                             "data": [{"id": ARGS.model, "object": "model"}]})
        else:
            self._send(200, {"status": "ok", "model": ARGS.model})

    def do_POST(self):
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self._send(404, {"error": {"message": "지원하지 않는 경로"}})
            return
        n = int(self.headers.get("Content-Length") or 0)
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
        except Exception as e:
            self._send(400, {"error": {"message": f"JSON 아님: {e}"}})
            return
        msgs = req.get("messages") or []
        if not msgs:
            self._send(400, {"error": {"message": "messages 가 비었습니다"}})
            return
        t0 = time.time()
        try:
            text, finish = generate(msgs,
                                    int(req.get("max_tokens") or 400),
                                    float(req.get("temperature", 0.9)))
        except Exception as e:
            self._send(500, {"error": {"message": f"생성 실패: {e}"}})
            return
        if not ARGS.quiet:
            print(f"  {time.time() - t0:5.1f}초  {text[:70]}", flush=True)
        self._send(200, {
            "id": "chatcmpl-local",
            "object": "chat.completion",
            "model": req.get("model") or ARGS.model,
            "choices": [{"index": 0, "finish_reason": finish,
                         "message": {"role": "assistant", "content": text}}],
        })

    def log_message(self, *a):        # 접속 로그는 끈다. 생성 로그만 본다
        pass


def main():
    global MODEL, TOK, ARGS
    # 윈도우 콘솔이 cp949 라 한글 밖 기호에서 죽는 일이 있다. 출력만 UTF-8 로 돌린다
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen2.5-7B-Instruct")
    ap.add_argument("--port", type=int, default=8501)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--quiet", action="store_true")
    ARGS = ap.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"모델 {ARGS.model} 를 {dev} 에 올립니다...", flush=True)
    t0 = time.time()
    TOK = AutoTokenizer.from_pretrained(ARGS.model)
    # V100 에는 bfloat16 이 없다. float16 으로 고정한다
    MODEL = AutoModelForCausalLM.from_pretrained(
        ARGS.model, torch_dtype=torch.float16 if dev == "cuda" else None)
    MODEL.to(dev).eval()
    print(f"  준비 {time.time() - t0:.1f}초", flush=True)
    if dev == "cuda":
        print(f"  VRAM {torch.cuda.memory_allocated() / 1024**3:.1f}GB "
              f"/ {torch.cuda.get_device_properties(0).total_memory / 1024**3:.0f}GB",
              flush=True)
    print(f"대기 중 - http://{ARGS.host}:{ARGS.port}/v1  (Ctrl+C 로 종료)", flush=True)
    ThreadingHTTPServer((ARGS.host, ARGS.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
