# CivicTrack — Civic Issue Reporting and Tracking System

A beginner-friendly Flask web application for citizens to report local civic issues and track their resolution. Administrators can review reports, assign departments, update statuses, and flag unresolved issues for escalation.

## Features

### Citizen
- Create an account and log in securely (passwords are hashed).
- Submit a civic complaint with title, category, description and address.
- Capture GPS coordinates using browser geolocation or by dropping a pin on the interactive OpenStreetMap map.
- Reverse-geocode selected coordinates to a readable address using the OpenStreetMap Nominatim API.
- Automatically read GPS/EXIF coordinates from uploaded photos when the original image contains that metadata.
- Optionally attach a photo (PNG/JPG/JPEG/GIF/WEBP, max 5 MB).
- Receive a unique complaint ticket ID.
- View complaint history and current status.
- Open captured coordinates in Google Maps.
- Escalate an unresolved complaint.

### Administrator
- Admin dashboard with total, open, resolved and escalated counts.
- Search by ticket ID, title, citizen name or address.
- Filter by complaint status.
- View citizen and complaint details.
- Assign a department, update status, and add an official note.

## Requirements
- Python 3.9 or newer
- pip
- A modern browser
- VS Code (recommended)

## Run on Windows (PowerShell)

1. Extract `civic_issue_tracker.zip`.
2. Open the extracted `civic_issue_tracker` folder in VS Code.
3. Open Terminal → New Terminal.
4. Create a virtual environment:

   ```powershell
   py -m venv venv
   ```

5. Activate it:

   ```powershell
   .\venv\Scripts\Activate.ps1
   ```

   If PowerShell blocks activation, run this once in that terminal and activate again:

   ```powershell
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   .\venv\Scripts\Activate.ps1
   ```

6. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

7. Start the app:

   ```powershell
   python app.py
   ```

8. Open the address shown in the terminal, normally `http://127.0.0.1:5000`.

The interactive map uses Leaflet + OpenStreetMap tiles; address lookup uses the OpenStreetMap Nominatim reverse-geocoding API and requires internet access. Browser geolocation requires permission and normally works on localhost or HTTPS. Photo GPS can only be detected if the uploaded original photo has EXIF GPS metadata; many messaging/social apps strip it. If metadata is missing, use browser GPS or click the map to pin the location.

The SQLite database (`civic_issues.db`) is created automatically on first run. The `uploads` folder stores complaint photos.

## Demo administrator login

- Email: `admin@civic.local`
- Password: `Admin@123`

Register through the separate Citizen or Admin option. Admin self-registration requires the setup code `CIVIC-ADMIN-2026` by default; set the `ADMIN_REGISTRATION_CODE` environment variable to a private value before sharing/deployment. The pre-created demo administrator remains available.

## Important before deployment

This is a student/demo project, not a production-ready municipal service. Before public deployment:
- Change `SECRET_KEY` to a long random secret in an environment variable.
- Change or remove the demo admin account and use a strong unique password.
- Turn off Flask debug mode (`debug=False`).
- Add CSRF protection, rate limiting, email/OTP verification and audit logs.
- Validate uploaded image contents, add malware scanning, and store uploads outside the public web root.
- Use HTTPS and a production WSGI server.
- Add privacy/consent notices and a retention policy for personal data and GPS coordinates.
- Configure real municipal department workflows and notification services if required.

## Project structure

```text
civic_issue_tracker/
├── app.py
├── requirements.txt
├── README.md
├── civic_issues.db       # created after first run
├── uploads/              # uploaded photos
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── register.html
│   ├── login.html
│   ├── dashboard.html
│   ├── new_complaint.html
│   ├── complaint_detail.html
│   ├── admin.html
│   └── error.html
└── static/
    ├── css/style.css
    └── js/app.js
```

## Notes
- GPS capture requires the user to grant browser location permission. Browsers generally allow geolocation on `localhost` and secure HTTPS origins.
- A readable address is still required; GPS coordinates are optional.
- The escalation feature flags a complaint for administrator attention. It does not automatically contact a government office.
