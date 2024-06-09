import sqlite3
from flask import g, Flask, request, jsonify, make_response
import os
import logging
import time


DATABASE = 'database.db'
WEBHOOK_USERNAME = os.environ.get("WEBHOOK_USERNAME", "DUMMY") # the dummy value is just so we can run the chron.py file without this env var
WEBHOOK_PASSWORD = os.environ.get("WEBHOOK_PASSWORD", "DUMMY")
LOGNAME = "app.log.txt"

# we may have 2 types of loggers (the one for flask and this one)?
# not sure.
logger = logging.getLogger(__name__)
logging.basicConfig(filename=LOGNAME,
                    filemode='a',
                    format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
                    datefmt='%H:%M:%S',
                    level=logging.DEBUG)


app = Flask(__name__)

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    return db

def init_db():
    get_db().execute("""
    CREATE TABLE IF NOT EXISTS webhooks (
        timestamp REAL,
        semester TEXT,
        section_full_code TEXT,
        prev_status TEXT,
        status TEXT
    );
    """)
    get_db().execute("""
    CREATE TABLE IF NOT EXISTS opendata_polling (
        timestamp REAL,
        semester TEXT,
        section_full_code TEXT,
        status TEXT
    );
    """)
    get_db().execute("""
    CREATE TABLE IF NOT EXISTS path_at_penn_polling (
        timestamp REAL,
        semester TEXT,
        section_full_code TEXT,
        status TEXT
    );
    """)

# initialize db
with app.app_context():
    init_db()

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

@app.route("/webhook")
def receive_webhook():
    auth_header = request.headers.get("Authorization", "")
    username, password = extract_basic_auth(auth_header)
    if username != WEBHOOK_USERNAME or password != WEBHOOK_PASSWORD:
        logger.error("Credentials could not be verified")
        return make_response(
            """Your credentials cannot be verified.
            They should be placed in the header as "Authorization-Bearer",
            YOUR_APP_ID and "Authorization-Token", YOUR_TOKEN""",
            401
        )

    if request.method != "POST":
        logger.error("Methods other than POST are not allowed")
        return make_response("Methods other than POST are not allowed", 405)

    if "json" not in request.content_type.lower():
        logger.error("Request expected in JSON")
        return make_response("Request expected in JSON", 415)

    try:
        data = json.loads(request.data)
    except json.JSONDecodeError:
        logger.error("Error decoding JSON body")
        return make_response("Error decoding JSON body", 400)

    course_id = data.get("section_id_normalized", None)
    if course_id is None:
        logger.error("Course ID could not be extracted from response")
        return make_response("Course ID could not be extracted from response", 400)

    course_status = data.get("status", None)
    if course_status is None:
        logger.error("Course Status could not be extracted from response")
        return make_response("Course Status could not be extracted from response", 400)

    prev_status = data.get("previous_status", None) or ""

    try:
        course_term = data.get("term", None)
        if course_term is None:
            logger.error("Course Term could not be extracted from response")
            return make_response("Course Term could not be extracted from response", 400)
        if any(course_term.endswith(s) for s in ["10", "20", "30"]):
            course_term = translate_semester_inv(course_term)
        if course_term.upper().endswith("B"):
            logger.error("webhook ignored (summer class)")
            return jsonify({"message": "webhook ignored (summer class)"})

        u = record_update(
            section,
            course_term,
            prev_status,
            course_status,
            alert_for_course_called,
            request.data,
        )
        update_course_from_record(u)
    except (ValueError) as e:
        logger.error(e, extra={"request": request})
        response = jsonify({"message": "We got an error but webhook should ignore it"}), 200

    return response
