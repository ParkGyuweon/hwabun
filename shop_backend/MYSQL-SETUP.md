# Shop Backend MySQL 실행

`shop_backend` 디렉터리에서 실행합니다.

```powershell
cd C:\Users\SSAFY\project2\S15P21A306\shop_backend
docker compose -f docker-compose.mysql.yml up -d
docker compose -f docker-compose.mysql.yml ps
```

호스트 접속 주소는 `localhost:3306` 또는 `localhost:13306`입니다. 기본 정보는 database `shop_backend`, user `shop_backend`, password `shop_backend_dev`이며 root 비밀번호는 `shop_backend_root_dev`입니다.

EC2 배포에서는 `SHOP_BACKEND_MYSQL_BIND_ADDRESS`를 EC2-1 사설 IP로 지정하고,
EC2-2 Spark가 `EC2-1_PRIVATE_IP:13306`으로 DW를 적재하도록 합니다. `13306`은
AWS 보안 그룹과 UFW에서 EC2-2 사설 IP에만 허용해야 합니다.

EC2-1의 `.env` 예시:

```dotenv
SHOP_BACKEND_MYSQL_BIND_ADDRESS=172.26.8.48
SHOP_BACKEND_MYSQL_PORT=13306
```

기본값은 `127.0.0.1`이므로 사설 IP를 지정하지 않으면 외부 EC2에서 접근할 수 없습니다.

포트 충돌 시 다음처럼 변경할 수 있습니다.

```powershell
$env:SHOP_BACKEND_MYSQL_PORT = "13307"
docker compose -f docker-compose.mysql.yml up -d
```

`mysql-erd.sql`은 MySQL 초기화 디렉터리에 마운트되어 데이터 볼륨이 비어 있는 첫 시작 때 38개 테이블을 자동 생성합니다. 이미 실행한 뒤 SQL을 수정했다면 자동 재실행되지 않습니다. 기존 데이터를 유지한 채 피드백 알림 스키마만 추가하려면 다음 migration을 실행합니다.

```powershell
Get-Content .\migrations\20260918_add_feedback_notifications.sql -Raw |
  docker exec -i shop-backend-mysql mysql -u root -pshop_backend_root_dev shop_backend
```

새 DB를 초기화할 때만 전체 DDL을 적용합니다.

```powershell
Get-Content .\mysql-erd.sql -Raw | docker exec -i shop-backend-mysql mysql -u root -pshop_backend_root_dev
```

개발 데이터를 모두 삭제하고 처음부터 다시 만들 때만 사용합니다.

```powershell
docker compose -f docker-compose.mysql.yml down -v
docker compose -f docker-compose.mysql.yml up -d
```

`down -v`는 `shop-backend-mysql-data` 볼륨의 모든 테이블과 데이터를 삭제합니다.

테이블 확인:

```powershell
docker exec shop-backend-mysql mysql -u shop_backend -pshop_backend_dev -D shop_backend -e "SHOW TABLES;"
docker logs shop-backend-mysql
```

같은 Docker 네트워크에서 애플리케이션이 접속할 때는 호스트 포트가 아니라 `shop-backend-mysql:3306`을 사용합니다.


