package com.cosmetic.shopbackend.security;

import com.cosmetic.shopbackend.identity.AccountRole;
import com.cosmetic.shopbackend.identity.AccountStatus;
import com.cosmetic.shopbackend.identity.MemberRepository;
import jakarta.servlet.*;
import jakarta.servlet.http.*;
import java.io.IOException;
import java.util.List;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class JwtAuthenticationFilter extends OncePerRequestFilter {

  private final JwtTokenService tokens;
  private final MemberRepository members;

  public JwtAuthenticationFilter(JwtTokenService t, MemberRepository m) {
    tokens = t;
    members = m;
  }

  @Override
  protected void doFilterInternal(
    HttpServletRequest req,
    HttpServletResponse res,
    FilterChain chain
  ) throws ServletException, IOException {
    String h = req.getHeader("Authorization");
    if (
      SecurityContextHolder.getContext().getAuthentication() == null &&
      h != null &&
      h.startsWith("Bearer ")
    ) try {
      ShopPrincipal p = tokens.parse(h.substring(7));
      if (activeAccount(p)) {
        var auth = new UsernamePasswordAuthenticationToken(
          p,
          null,
          List.of(new SimpleGrantedAuthority("ROLE_" + p.role().name()))
        );
        SecurityContextHolder.getContext().setAuthentication(auth);
      }
    } catch (RuntimeException ignored) {}
    chain.doFilter(req, res);
  }

  /**
   * 회원 토큰은 서명·만료만으로 믿지 않고, 지금도 ACTIVE 인 회원인지 PK 로 한 번 확인한다.
   * 탈퇴(WITHDRAWN)·정지된 회원의 토큰이 만료(최대 24시간)까지 살아 있으면 안 되기 때문이다.
   * 인증을 세우지 않으면 보호된 경로는 보안 설정의 401 {"error":"unauthorized"} 로 끝난다.
   *
   * 판매자·관리자 토큰은 지금처럼 서명·만료만 본다 (그쪽에는 탈퇴가 없다).
   */
  private boolean activeAccount(ShopPrincipal p) {
    if (p.role() != AccountRole.MEMBER) return true;
    return members
      .findStatusById(p.accountId())
      .map(AccountStatus.ACTIVE::equals)
      .orElse(false);
  }
}
