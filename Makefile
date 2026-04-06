# Test ortamı yönetimi
# Kullanım: make <komut>
# Windows'ta: mingw32-make veya WSL içinde make

.PHONY: up down seed reset migrate run logs help

## Postgres + Adminer'ı başlat
up:
	docker compose up -d
	@echo "Postgres: localhost:5432"
	@echo "Adminer:  http://localhost:8080  (server=postgres, user=avukat_user, pass=avukat_pass, db=avukat_list)"

## Servisleri durdur
down:
	docker compose down

## Migrate + seed (ilk kurulum)
seed: up
	python manage.py migrate --noinput
	python manage.py seed_test_data --excel
	@echo ""
	@echo "Sunucuyu başlatmak için: make run"

## Veritabanını sıfırla ve yeniden seed et
reset: up
	python manage.py flush --no-input
	python manage.py migrate --noinput
	python manage.py seed_test_data --reset --excel

## Sadece migrate
migrate:
	python manage.py migrate --noinput

## Django sunucusunu başlat
run:
	python manage.py runserver

## Docker loglarını takip et
logs:
	docker compose logs -f postgres

## Yardım
help:
	@echo ""
	@echo "  make up      — Postgres + Adminer başlat"
	@echo "  make seed    — İlk kurulum (migrate + test verisi)"
	@echo "  make reset   — DB sıfırla + yeniden seed et"
	@echo "  make run     — Django sunucusu"
	@echo "  make down    — Docker durdur"
	@echo ""
