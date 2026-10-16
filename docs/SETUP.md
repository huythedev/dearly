# Set up Dearly

[All guides](README.md) · [Using Dearly](USAGE.md) · [Hosting and backups](DEPLOYMENT.md)

## Web app with Docker

Install Git and Docker with Docker Compose, then start Docker. On macOS/Windows, Docker Desktop includes Compose; on Linux, use Docker Engine with the Compose plugin.

From a terminal or PowerShell:

```bash
git clone https://github.com/huythedev/dearly.git
cd dearly
docker compose up -d --build
```

Open [http://localhost:8003](http://localhost:8003) and choose **Create account**. The backend runs on port **8002**. For later commands in this guide, stay in the `dearly` repository folder unless a step says otherwise.

To check startup:

```bash
docker compose ps
docker compose logs -f
```

Press **Ctrl+C** to stop following the logs; the containers keep running.

### Choose your ports and backend

You can use the defaults without a configuration file. To customize them, copy [`.env.example`](../.env.example) to `.env` and edit it in a text editor.

If you have Python 3, you can use the interactive helper instead. It asks for the web port, backend port, and backend address. Press **Enter** to accept each default.

```bash
# macOS / Linux
python3 configure-docker.py
```

```powershell
# Windows
py -3 configure-docker.py
```

For both containers on the same machine, keep the backend address **`backend:8002`**. Existing `.env` values take precedence over defaults. Apply your settings with `docker compose up -d --build`.

See [custom ports](DEPLOYMENT.md#custom-ports) and [separate machines](DEPLOYMENT.md#frontend-and-backend-on-separate-machines) for examples.

## iOS app

You need a **Mac**, **Xcode 26 or newer**, and an iPhone or simulator running **iOS 17+**. This repository contains the Xcode project; build it with Xcode to install it.

1. Download the repository if you have not already, then open `ios/Dearly.xcodeproj` in Xcode.
2. Select the **Dearly** scheme and an iPhone simulator. For a physical iPhone, choose your device and configure your signing team in Xcode.
3. Press **⌘R** to build and run.
4. On the login screen, expand **Server connection / Kết nối server** and choose an address below.
5. Create an account or log in. Web and iOS share accounts when they connect to the same backend.

| Your server | Address to enter |
|---|---|
| Public Dearly deployment | `https://dearly.huythedev.com` |
| Full Docker setup on the simulator's Mac | `http://localhost:8003` |
| Python-only backend on the simulator's Mac | `http://localhost:8002` |
| Full Docker setup on another computer, from a physical iPhone | `http://COMPUTER_LAN_IP:8003` |

The public HTTPS address is the app's default; its availability depends on the server being deployed. A previously saved address or session takes precedence. Enter the base address without `/v1` or `/ws/chat`.

### Connect a physical iPhone on the same Wi-Fi

For the full Docker setup, set this in the root `.env` file:

```dotenv
DEARLY_FRONTEND_BIND=0.0.0.0
```

Then run `docker compose up -d frontend`. Enter the computer's LAN IP in the app, for example `http://192.168.1.10:8003`. Allow Local Network access on the iPhone when prompted. The computer's firewall must allow the chosen frontend port on your private network. `localhost` on the phone refers to the phone itself.

Use a **Debug** build for these local HTTP addresses. Release builds require HTTPS with a trusted certificate. For a Python-only server, use its LAN binding below and port **8002** instead.

## Backend without Docker

For iOS/API use, you can run the backend directly with **Python 3.11+**. SQLite is included; no separate database service or Node.js installation is needed.

From the repository root on macOS/Linux:

```bash
cd backend
python3 setup.py
.venv/bin/python run.py serve
```

On Windows PowerShell:

```powershell
cd backend
py -3 setup.py
.\.venv\Scripts\python.exe run.py serve
```

Setup creates `.venv` and installs dependencies. The API listens at [http://localhost:8002](http://localhost:8002); check [health](http://localhost:8002/health) or [API docs](http://localhost:8002/docs). Stop it with **Ctrl+C**.

For an iPhone on your LAN, start it with `.venv/bin/python run.py serve --host 0.0.0.0 --port 8002`; on Windows, use `.\.venv\Scripts\python.exe` instead. Connect to `http://COMPUTER_LAN_IP:8002`.

See the [backend reference](../backend/README.md) for database paths and command options. To run React without Docker, follow [local web development](DEVELOPMENT.md#local-web-development).

## Troubleshooting

| What happens | What to try |
|---|---|
| `docker compose` is unavailable or cannot connect | Install/start Docker and check that Compose is included. |
| The web page will not open | Run `docker compose ps` and `docker compose logs -f frontend backend`; use the frontend port from your `.env`. |
| A port is already in use | Change the published port in `.env`, then run `docker compose up -d`. The Python launcher also accepts `--port 8001`. |
| The web page opens but signup/login fails | Check backend logs and `DEARLY_BACKEND_ADDRESS`. In Compose, use `backend:8002`, not `localhost:8002`. |
| The iPhone cannot connect | Check Debug/HTTPS requirements, LAN IP, bind address, port, Local Network permission, firewall, and that both devices are on the same Wi-Fi. |
| Companion matching is unavailable | Ask your administrator to [review your date of birth](ADMINISTRATION.md#age-verification). You can use journals and community meanwhile. |
