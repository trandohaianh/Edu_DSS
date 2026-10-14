# Streamlit server recovery runbook

This setup keeps the app running with auto-restart and a healthcheck.

## 1) Start with auto-restart

```powershell
docker compose up -d --build
```

Check status:

```powershell
docker compose ps
```

If container crashes, Docker automatically restarts it (`restart: always`).

## 2) Basic monitoring

Watch logs in real time:

```powershell
docker compose logs -f streamlit-app
```

Health state:

```powershell
docker inspect --format "{{.State.Health.Status}}" streamlit-app
```

## 3) Fast incident recovery

Recreate container:

```powershell
docker compose down
docker compose up -d --build
```

Restart only:

```powershell
docker compose restart streamlit-app
```

## 4) Keep data safe on host

The compose file maps these host folders:

- `./uploads`
- `./models`
- `./data_warehouse`

So app/container restart does not lose those files.

## 5) Backup (daily example on Windows)

Use Task Scheduler to run:

```powershell
robocopy "D:\KLTN\code\uploads" "D:\KLTN\backups\uploads" /MIR /R:2 /W:5
robocopy "D:\KLTN\code\data_warehouse" "D:\KLTN\backups\data_warehouse" /MIR /R:2 /W:5
```

## 6) Optional: run `5.py` instead of `main.py`

In `docker-compose.yml`, change:

- `APP_FILE=main.py` -> `APP_FILE=5.py`

Then redeploy:

```powershell
docker compose up -d --build
```
