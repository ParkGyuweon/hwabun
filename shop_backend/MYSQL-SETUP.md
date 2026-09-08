# Shop Backend MySQL 실행

`shop_backend` 디렉터리에서 실행합니다.

```powershell
cd C:\Users\SSAFY\project2\S15P21A306\shop_backend
docker compose -f docker-compose.mysql.yml up -d
docker compose -f docker-compose.mysql.yml ps
```

호스트 접속 주소는 `localhost:13306`입니다. 기본 정보는 database `shop_backend`, user `shop_backend`, password `shop_backend_dev`이며 root 비밀번호는 `shop_backend_root_dev`입니다.

포트 충돌 시 다음처럼 변경할 수 있습니다.

```powershell
$env:SHOP_BACKEND_MYSQL_PORT = "13307"
docker compose -f docker-compose.mysql.yml up -d
```

`mysql-erd.sql`은 MySQL 초기화 디렉터리에 마운트되어 데이터 볼륨이 비어 있는 첫 시작 때 29개 테이블을 자동 생성합니다. 이미 실행한 뒤 SQL을 수정했다면 자동 재실행되지 않으므로 다음처럼 명시적으로 적용합니다.

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

같은 Docker 네트워크에서 애플리케이션이 접속할 때는 `localhost:13306`이 아니라 `shop-backend-mysql:3306`을 사용합니다.
