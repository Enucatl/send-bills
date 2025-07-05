# send-bills

## Install
```
uv pip install --python /opt/home/user/venv/send-bills/bin/python -e .[dev]
```

## Test
```
DATABASE_URL=$(vault kv get -mount=airflow -field=uri connections/djangodev) /opt/home/user/venv/send-bills/bin/python src/send_bills/manage.py test bills
```

## Run development server
```
DATABASE_URL=$(vault kv get -mount=airflow -field=uri connections/djangodev) /opt/home/user/venv/send-bills/bin/python src/send_bills/manage.py runserver
```

## Run development docker
```
VERSION=$(/opt/home/user/venv/send-bills/bin/python -m setuptools_git_versioning) docker compose --env-file .env up --build
```
