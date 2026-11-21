# City Events Finder (GCP Extra Credit Project)

A containerized web application built with **Flask** (a lightweight **Python** web framework) that lets users search a city and state to view upcoming local events sorted chronologically (soonest first) alongside a multi-day weather forecast.

## Context & Project Scope
- **Assignment Context:** Extra credit group project submission due at 11:59 PM.
- **Collaboration Note:** After multiple outreach attempts prior to the deadline, the group partner was unreachable, so local development, repository setup, **Secret Manager** configuration, **Artifact Registry** image build, and **Cloud Run** deployment configuration were completed solo.
- **Omitted Step (Step 5):** Putting an **External HTTP(S) (HyperText Transfer Protocol Secure, encrypted web traffic)** Load Balancer and **Serverless NEG (Network Endpoint Group, a routing backend that connects a load balancer to a serverless service)** in front of **Cloud Run** was intentionally omitted due to the extra credit scope, time constraints ahead of the 11:59 PM deadline, and avoiding ongoing hourly load balancer and static **IP (Internet Protocol, a network address)** charges.

## Data Sources & APIs (Application Programming Interfaces)
- **PredictHQ Events API:** Queries events within a 20-mile radius of geocoded city coordinates using a bearer token (`PREDICTHQ_API_KEY`). Replaced **SeatGeek** during development because SeatGeek API credentials were gated and slow to obtain.
- **Ticketmaster Discovery API:** Integrated in code (`TICKETMASTER_API_KEY`); safely returns an empty list (`[]`) until developer account approval completes, at which point adding the key activates dual-source merging without code changes.
- **Open-Meteo Geocoding & Forecast APIs:** Resolves city/state queries to latitude, longitude, and a display label, and returns current weather plus a 5-day forecast without requiring an API key.

## App Architecture & Deduplication Logic
- **Routes (`app.py`):**
  - `GET /`: Parses city and optional two-letter state code (`parse_location()`), geocodes coordinates via Open-Meteo (`geocode_city()`), fetches events from configured providers, deduplicates and sorts results, and renders `templates/index.html`.
  - `GET /health`: Returns `"OK"` with **HTTP (HyperText Transfer Protocol)** status `200` for local verification and **Cloud Run** startup/liveness probes.
- **Merging & Duplicate Removal:** `merge_and_deduplicate()` keys events by `(normalize_title(title), local_date)`—lowercasing titles, stripping non-alphanumeric characters except whitespace via regular expressions, and collapsing extra spaces. Matching same-day events are merged into one entry with combined source labels (such as `"Ticketmaster & PredictHQ"`), and the final list is sorted ascending by `date_iso` (soonest first).

## Repository Structure
- `app.py`: **Flask** application, location parser, external API clients, deduplication, and date sorting.
- `templates/index.html`: Responsive **HTML (HyperText Markup Language)** and **CSS (Cascading Style Sheets)** interface with a centered search bar, date-sorted event cards, and a side-by-side weather forecast panel.
- `requirements.txt`: **Python** dependencies (`flask`, `requests`, `python-dotenv`, `gunicorn`).
- `Dockerfile`: Builds a `python:3.12-slim` container running **Gunicorn** (Green Unicorn, a production **WSGI**, or Web Server Gateway Interface, server for Python) bound to `$PORT` (default `8080`).
- `.gitignore`: Excludes `.env`, `venv/`, `__pycache__/`, `*.pyc`, and `.DS_Store` so local secrets and virtual environments are never committed to **Git (a distributed version control system)**.
- `.env.example`: Template documenting expected environment variables (`PORT`, `DEFAULT_CITY`, `TICKETMASTER_API_KEY`, `PREDICTHQ_API_KEY`) without real credentials.

## Local Setup & Run Instructions (Checkpoint 1)
1. Clone the repository and enter the project directory:
    ```bash
   git clone [https://github.com/garrisongvcu/city-events-finder.git](https://github.com/garrisongvcu/city-events-finder.git)
   cd city-events-finder```
Create and activate a virtual environment, then install dependencies:
    ```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt```

Add PREDICTHQ_API_KEY (and TICKETMASTER_API_KEY once approved) inside .env. Never commit .env.

Start the local server: 
    ```bash
python3 app.py```

## Verify endpoints in  browser:

http://localhost:8080/health → returns OK (200 OK)
http://localhost:8080/?q=Richmond → displays sorted events and the Open-Meteo weather forecast

## GCP (Google Cloud Platform) Deployment Steps
1: Project, Budget Alert, & APIs: Selected project city-events-finder-2026, configured a billing budget alert with email thresholds (50%, 90%, 100%), and enabled Artifact Registry API, Cloud Build API, Cloud Run Admin API, Secret Manager API, and Compute Engine API.

2: Secret Manager: Created secret PREDICTHQ_API_KEY with automatic replication so zero API keys are stored in code, Dockerfiles, or Git history.

3: Artifact Registry & Cloud Build: Created Docker repository events-finder-repo in us-east4 and built/pushed the container image via Cloud Build:
  gcloud config set project city-events-finder-2026
  gcloud builds submit --tag us-east4-docker.pkg.dev/city-events-finder-2026/events-finder-repo/city-   events-app:v1

4: IAM & Cloud Run Deployment: Granted roles/secretmanager.secretAccessor on PREDICTHQ_API_KEY to the runtime service account (285638961075-compute@developer.gserviceaccount.com) and configured Cloud Run in us-east4 with:
-Container image: us-east4-docker.pkg.dev/city-events-finder-2026/events-finder-repo/city-events-app:v1
-Container port: 8080
-Health probe: GET /health
-Environment variable: DEFAULT_CITY=Richmond
-Secret reference: PREDICTHQ_API_KEY=PREDICTHQ_API_KEY:latest
-Autoscaling: Min instances = 0 (scales to zero when idle), Max instances = 5, Concurrency = 80

## Issues Encountered & Adjustments Made

1: Accidental Home-Directory Git Initialization & Author Identity: Git was initially initialized in /Users/gregorygarrison/ (~) with a machine-generated author identity and only README.md pushed. Removed ~/.git, created ~/city-events-finder, moved README.md into it, set Git user.name (Gregory Garrison) and user.email (garrisong@vcu.edu), and pushed cleanly to origin/main.

2: SeatGeek API Gating → PredictHQ Substitution: Because SeatGeek developer keys required gated approval, substituted PredictHQ (PREDICTHQ_API_KEY) as the active event provider while keeping Ticketmaster wired in code ([] fallback until approved) and Open-Meteo for weather enrichment.

3: Python 3.9 Type Union TypeError & macOS python3 Command: Running app.py locally threw TypeError: unsupported operand type(s) for |: 'type' and 'NoneType' on dict | None because the local virtual environment ran Python 3.9 rather than 3.10+, causing ERR_CONNECTION_REFUSED on /health. Updated annotations to Optional[dict] from typing, recreated the virtual environment with python3 -m venv venv (after python3.12 and python were not found in macOS zsh), and verified 200 OK on /health and /?q=Richmond.

4: Cloud Shell SSH Key Error → HTTPS Clone: Cloning over SSH (Secure Shell, an encrypted network protocol for remote access and Git authentication) in Cloud Shell (a browser-based terminal inside GCP) failed with Permission denied (publickey). Switched to cloning over https://github.com/garrisongvcu/city-events-finder.git, allowing gcloud builds submit to complete (STATUS: SUCCESS in 31s).

5: Secret Manager IAM Permission & Region Alignment: Initial Cloud Run deployment failed with Permission denied on PREDICTHQ_API_KEY because 285638961075-compute@developer.gserviceaccount.com lacked roles/secretmanager.secretAccessor, and an initial service was created in europe-west1. Granted roles/secretmanager.secretAccessor on the secret and aligned Cloud Run to us-east4 to match the Artifact Registry image location.

## To keep charges near zero after grading, I will delete the Cloud Run service, Artifact Registry repository, and Secret Manager secret (or delete the city-events-finder-2026 project):
  ```bash
  gcloud config set project city-events-finder-2026
  gcloud run services delete city-events-app --region=us-east4 --quiet
  gcloud artifacts repositories delete events-finder-repo --location=us-east4 --quiet
  gcloud secrets delete PREDICTHQ_API_KEY --quiet```
