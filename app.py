import os
import sqlite3
import uuid
import re
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, flash, session, g, abort, jsonify
try:
    from PIL import Image
except ImportError:
    Image = None

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "civic_issues.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-key-before-deployment")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

STATUSES = ["Submitted", "Assigned", "In Progress", "Resolved", "Rejected"]
CATEGORIES = ["Road/Pothole", "Garbage", "Water Leakage", "Streetlight", "Drainage", "Public Safety", "Other"]

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(_error):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db = sqlite3.connect(DATABASE)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'citizen',
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS complaints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_id TEXT NOT NULL UNIQUE,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        category TEXT NOT NULL,
        description TEXT NOT NULL,
        address TEXT NOT NULL,
        latitude REAL,
        longitude REAL,
        photo TEXT,
        status TEXT NOT NULL DEFAULT 'Submitted',
        department TEXT,
        admin_note TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        escalated INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    """)
    # Demo admin is created only when it does not already exist.
    existing = db.execute("SELECT id FROM users WHERE email = ?", ("admin@civic.local",)).fetchone()
    if not existing:
        db.execute(
            "INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",
            ("System Admin", "admin@civic.local", generate_password_hash("Admin@123"), "admin", datetime.now().isoformat(timespec="seconds"))
        )
    db.commit()
    db.close()

# Create the SQLite tables on import as well as when run directly, so the app
# also works with Flask test clients and WSGI servers.
init_db()

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            abort(403)
        return fn(*args, **kwargs)
    return wrapper

def _exif_float(value):
    try: return float(value)
    except Exception: return float(value.numerator) / float(value.denominator)

def extract_photo_gps(photo):
    """Return embedded EXIF GPS coordinates, or (None, None) if absent."""
    if Image is None or not photo:
        return None, None
    try:
        photo.stream.seek(0)
        exif = Image.open(photo.stream).getexif()
        try:
            gps = exif.get_ifd(34853)
        except Exception:
            gps = exif.get(34853)
        if not gps: return None, None
        gps = dict(gps)
        lat, lat_ref = gps.get(2), gps.get(1)
        lon, lon_ref = gps.get(4), gps.get(3)
        if not (lat and lat_ref and lon and lon_ref): return None, None
        latitude = _exif_float(lat[0]) + _exif_float(lat[1])/60 + _exif_float(lat[2])/3600
        longitude = _exif_float(lon[0]) + _exif_float(lon[1])/60 + _exif_float(lon[2])/3600
        if str(lat_ref).upper().startswith('S'): latitude = -latitude
        if str(lon_ref).upper().startswith('W'): longitude = -longitude
        return latitude, longitude
    except Exception:
        return None, None
    finally:
        try: photo.stream.seek(0)
        except Exception: pass

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return render_template("index.html")

@app.route("/register")
def register_choice():
    return render_template("register_choice.html")


@app.route("/register/<role>", methods=["GET", "POST"])
def register(role):
    if role not in ("citizen", "admin"):
        abort(404)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        admin_code = request.form.get("admin_code", "")
        if not name or len(name) > 100 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or len(password) < 8:
            flash("Enter a valid name and email. Password must be at least 8 characters.", "danger")
            return render_template("register.html", role=role)
        if role == "admin":
            required_code = os.environ.get("ADMIN_REGISTRATION_CODE", "CIVIC-ADMIN-2026")
            if not admin_code or admin_code != required_code:
                flash("Invalid administrator registration code.", "danger")
                return render_template("register.html", role=role)
        try:
            db = get_db()
            db.execute("INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                       (name, email, generate_password_hash(password), role, datetime.now().isoformat(timespec="seconds")))
            db.commit()
            flash(f"{role.title()} account created. Please log in.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("An account with that email already exists.", "danger")
    return render_template("register.html", role=role)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]
            return redirect(url_for("admin_dashboard" if user["role"] == "admin" else "dashboard"))
        flash("Invalid email or password.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))

@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    if session.get("role") == "admin":
        return redirect(url_for("admin_dashboard"))
    complaints = db.execute(
        "SELECT * FROM complaints WHERE user_id = ? ORDER BY created_at DESC",
        (session["user_id"],)
    ).fetchall()
    counts = db.execute(
        "SELECT status, COUNT(*) AS total FROM complaints WHERE user_id = ? GROUP BY status",
        (session["user_id"],)
    ).fetchall()
    return render_template("dashboard.html", complaints=complaints, counts={r["status"]: r["total"] for r in counts})

@app.route("/complaint/new", methods=["GET", "POST"])
@login_required
def new_complaint():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        category = request.form.get("category", "")
        description = request.form.get("description", "").strip()
        address = request.form.get("address", "").strip()
        lat = request.form.get("latitude") or None
        lng = request.form.get("longitude") or None
        photo_name = None
        photo = request.files.get("photo")
        # If browser GPS was not supplied, try reading GPS coordinates from photo EXIF.
        if photo and photo.filename and (not lat or not lng):
            photo_lat, photo_lng = extract_photo_gps(photo)
            if photo_lat is not None and photo_lng is not None:
                lat, lng = photo_lat, photo_lng
        if not title or len(title) > 120 or category not in CATEGORIES or not description or len(description) > 1500 or not address:
            flash("Please complete all required fields and keep within the stated length limits.", "danger")
            return render_template("new_complaint.html", categories=CATEGORIES)
        try:
            lat = float(lat) if lat is not None else None
            lng = float(lng) if lng is not None else None
            if lat is not None and not -90 <= lat <= 90:
                raise ValueError
            if lng is not None and not -180 <= lng <= 180:
                raise ValueError
        except (TypeError, ValueError):
            flash("The captured coordinates are invalid. Please try location capture again.", "danger")
            return render_template("new_complaint.html", categories=CATEGORIES)
        if photo and photo.filename:
            if not allowed_file(photo.filename):
                flash("Photo must be PNG, JPG, JPEG, GIF, or WEBP.", "danger")
                return render_template("new_complaint.html", categories=CATEGORIES)
            ext = secure_filename(photo.filename).rsplit(".", 1)[1].lower()
            photo_name = f"{uuid.uuid4().hex}.{ext}"
            photo.save(os.path.join(UPLOAD_FOLDER, photo_name))
        now = datetime.now().isoformat(timespec="seconds")
        ticket = "CIV-" + uuid.uuid4().hex[:8].upper()
        db = get_db()
        db.execute("""
            INSERT INTO complaints(ticket_id,user_id,title,category,description,address,latitude,longitude,photo,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """, (ticket, session["user_id"], title, category, description, address, lat, lng, photo_name, now, now))
        db.commit()
        flash(f"Complaint submitted successfully. Your ticket ID is {ticket}.", "success")
        return redirect(url_for("dashboard"))
    return render_template("new_complaint.html", categories=CATEGORIES)

@app.route("/api/reverse-geocode")
def reverse_geocode():
    """Look up a human-readable address for a map pin with OpenStreetMap Nominatim."""
    try:
        import requests
        lat, lon = float(request.args.get("lat", "")), float(request.args.get("lon", ""))
        if not (-90 <= lat <= 90 and -180 <= lon <= 180): raise ValueError
        response = requests.get("https://nominatim.openstreetmap.org/reverse",
            params={"format": "jsonv2", "lat": lat, "lon": lon},
            headers={"User-Agent": "CivicTrackStudentProject/1.0"}, timeout=8)
        response.raise_for_status()
        return jsonify({"address": response.json().get("display_name", "")})
    except Exception:
        return jsonify({"address": "", "message": "Address lookup unavailable; type the address manually."})

@app.route("/uploads/<path:filename>")
@login_required
def uploaded_file(filename):
    # Only complaint owners and admins should see complaint photos.
    from flask import send_from_directory
    db = get_db()
    row = db.execute("SELECT user_id FROM complaints WHERE photo=?", (filename,)).fetchone()
    if not row:
        abort(404)
    if session.get("role") != "admin" and row["user_id"] != session["user_id"]:
        abort(403)
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route("/complaint/<int:complaint_id>")
@login_required
def complaint_detail(complaint_id):
    complaint = get_db().execute("""
        SELECT c.*, u.name AS citizen_name, u.email AS citizen_email
        FROM complaints c JOIN users u ON u.id = c.user_id WHERE c.id = ?
    """, (complaint_id,)).fetchone()
    if not complaint:
        abort(404)
    if session.get("role") != "admin" and complaint["user_id"] != session["user_id"]:
        abort(403)
    return render_template("complaint_detail.html", complaint=complaint, statuses=STATUSES)

@app.route("/admin")
@login_required
@admin_required
def admin_dashboard():
    db = get_db()
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()
    sql = """SELECT c.*, u.name AS citizen_name, u.email AS citizen_email
             FROM complaints c JOIN users u ON u.id=c.user_id WHERE 1=1"""
    params = []
    if q:
        sql += " AND (c.ticket_id LIKE ? OR c.title LIKE ? OR u.name LIKE ? OR c.address LIKE ?)"
        params += [f"%{q}%"] * 4
    if status in STATUSES:
        sql += " AND c.status = ?"
        params.append(status)
    sql += " ORDER BY c.created_at DESC"
    complaints = db.execute(sql, params).fetchall()
    totals = db.execute("SELECT COUNT(*) AS total FROM complaints").fetchone()["total"]
    open_count = db.execute("SELECT COUNT(*) AS total FROM complaints WHERE status NOT IN ('Resolved','Rejected')").fetchone()["total"]
    resolved = db.execute("SELECT COUNT(*) AS total FROM complaints WHERE status='Resolved'").fetchone()["total"]
    escalated = db.execute("SELECT COUNT(*) AS total FROM complaints WHERE escalated=1").fetchone()["total"]
    map_rows = db.execute("""SELECT id,ticket_id,title,category,address,latitude,longitude,status
                             FROM complaints WHERE latitude IS NOT NULL AND longitude IS NOT NULL
                             ORDER BY created_at DESC""").fetchall()
    map_complaints = [dict(row) for row in map_rows]
    return render_template("admin.html", complaints=complaints, statuses=STATUSES, q=q, selected_status=status,
                           totals=totals, open_count=open_count, resolved=resolved, escalated=escalated,
                           map_complaints=map_complaints)

@app.route("/admin/complaint/<int:complaint_id>/update", methods=["POST"])
@login_required
@admin_required
def update_complaint(complaint_id):
    status = request.form.get("status", "")
    department = request.form.get("department", "").strip()
    note = request.form.get("admin_note", "").strip()
    if status not in STATUSES:
        flash("Invalid status.", "danger")
        return redirect(url_for("complaint_detail", complaint_id=complaint_id))
    db = get_db()
    exists = db.execute("SELECT id FROM complaints WHERE id=?", (complaint_id,)).fetchone()
    if not exists:
        abort(404)
    db.execute("""UPDATE complaints SET status=?, department=?, admin_note=?, updated_at=? WHERE id=?""",
               (status, department or None, note or None, datetime.now().isoformat(timespec="seconds"), complaint_id))
    db.commit()
    flash("Complaint updated.", "success")
    return redirect(url_for("complaint_detail", complaint_id=complaint_id))

@app.route("/complaint/<int:complaint_id>/escalate", methods=["POST"])
@login_required
def escalate_complaint(complaint_id):
    db = get_db()
    complaint = db.execute("SELECT * FROM complaints WHERE id=?", (complaint_id,)).fetchone()
    if not complaint:
        abort(404)
    if session.get("role") != "admin" and complaint["user_id"] != session["user_id"]:
        abort(403)
    if complaint["status"] in ("Resolved", "Rejected"):
        flash("Closed complaints cannot be escalated.", "warning")
    else:
        db.execute("UPDATE complaints SET escalated=1, updated_at=? WHERE id=?",
                   (datetime.now().isoformat(timespec="seconds"), complaint_id))
        db.commit()
        flash("Complaint marked for escalation.", "success")
    return redirect(url_for("complaint_detail", complaint_id=complaint_id))

@app.errorhandler(403)
def forbidden(_error):
    return render_template("error.html", code=403, message="You do not have permission to view this page."), 403

@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html", code=404, message="The requested page could not be found."), 404

@app.errorhandler(413)
def too_large(_error):
    flash("File is too large. Maximum upload size is 5 MB.", "danger")
    return redirect(request.referrer or url_for("dashboard"))

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1")
