web: python manage.py migrate && python manage.py collectstatic --noinput && python manage.py setup_auth --admin-username=admin --admin-password=admin && gunicorn core.wsgi --bind 0.0.0.0:$PORT
