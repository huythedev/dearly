# Dearly 🌱

A quiet place to write, find someone willing to listen, and grow a little garden together. Use Dearly on the web or iOS, with the same account on the same server.

## Get started with Docker

You need **Git** and **Docker with Docker Compose**. Start Docker before running these commands. They work in a terminal on macOS/Linux or PowerShell on Windows.

### 1. Download Dearly

```bash
git clone https://github.com/huythedev/dearly.git
cd dearly
```

### 2. Start the app

```bash
docker compose up -d --build
```

The first build may take a few minutes. Docker starts both the web app and its backend.

### 3. Open Dearly

Go to **[http://localhost:8003](http://localhost:8003)**, choose **Create account**, and sign up. Dearly is for ages **16 and up**.

The default ports are **8003 for web** and **8002 for the backend**. To change them, use another backend, or connect from a phone, follow the [setup guide](docs/SETUP.md).

## Your first few minutes

On your first login, choose **Show me around** for a short interactive tour on web or iOS. You can skip it and open **Take a guided tour** in account settings whenever you like.

1. Open **My journal** and write an entry. New entries are private by default.
2. To share, choose **Companion** or **Community** and review the sharing preview before saving.
3. Visit **Companion** to find someone to connect with. An administrator must review your date of birth before matching is available.
4. Once connected, chat and check in together in **Our garden**.

You can choose English or Vietnamese and switch between light, dark, and system appearance. The [user guide](docs/USAGE.md) explains sharing, connections, gardens, and settings.

Save your **recovery code** in account settings before using another device. New private journal text and companion conversations use end-to-end encryption. Settings also provides **Download my data** and **Delete my account**. Follow the [privacy and recovery guide](docs/ENCRYPTION.md) for setup and details.

## Use Dearly on iPhone

Build the app on a Mac with Xcode, then connect it to your Dearly server. Follow the [iOS setup instructions](docs/SETUP.md#ios-app) for the simulator, a physical iPhone, or the public server address.

## Update or stop your installation

For an existing installation, [back up your data and follow the update steps](docs/DEPLOYMENT.md#updates-and-backups).

To stop Dearly, run this from the repository folder:

```bash
docker compose down
```

Your saved data stays in the Docker volume. To start again, run `docker compose up -d`.

## More help

| I want to… | Guide |
|---|---|
| Change setup options or fix a connection problem | [Setup and troubleshooting](docs/SETUP.md) |
| Learn how to use Dearly | [User guide](docs/USAGE.md) |
| Host Dearly, configure ports/tunnel, or make a backup | [Deployment guide](docs/DEPLOYMENT.md) |
| Set up an administrator or manage reports and age verification | [Administration guide](docs/ADMINISTRATION.md) |
| Work on the code or run checks | [Development guide](docs/DEVELOPMENT.md) |

See [all documentation](docs/README.md) for API, privacy/security behavior, localization, and the roadmap.

Dearly is a space for companionship, not a therapy service. Licensed under the [MIT License](LICENSE). Copyright (c) 2026 Huy Nguyen.
