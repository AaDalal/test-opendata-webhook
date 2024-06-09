import requests
from app import app  
from course_list import course_list
import logging 
import time
from urllib.parse import quote

LOGNAME = "chron.logs.txt"
POLLING_INTERVAL_SECONDS = 600
PATH_AT_PENN_SEMESTER = "202430" # semester in path@penn form

logging.basicConfig(filename=LOGNAME,
                    filemode='a',
                    format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
                    datefmt='%H:%M:%S',
                    level=logging.DEBUG)
logger = logging.getLogger(__name__)

logger.error("HEY")

# make sure tables are defined
with app.app_context():
    from app import init_db
    init_db()
    del init_db # it's not actually valid past this context

def status_on_path_at_penn(
    course_code,
    path_at_penn_semester=PATH_AT_PENN_SEMESTER
):
    # Note: this api is actually unauthenticated as far as I can tell
    # so no cookies needed!

    # turn STAT-4700 into STAT 4700
    course_code = " ".join(course_code.split("-"))

    headers = {
        'accept': 'application/json, text/javascript, */*; q=0.01',
        'accept-language': 'en-US,en;q=0.9',
        'content-type': 'application/json',
        'origin': 'https://courses.upenn.edu',
        'priority': 'u=1, i',
        'referer': 'https://courses.upenn.edu/',
        'sec-ch-ua': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'x-requested-with': 'XMLHttpRequest',
    }

    params = {
        'page': 'fose',
        'route': 'search',
        'alias': course_code,
    }

    data = quote(f'{{"other":{{"srcdb":"{path_at_penn_semester}"}},"criteria":[{{"field":"alias","value":"{course_code}"}}]}}')
    response = requests.post('https://courses.upenn.edu/api/', params=params, headers=headers, data=data)
    logger.debug(
        f"path@penn response: {response.status_code} {response.json()}"
    )
    if response.ok:
        logging.info(response.json)
        return {
            ("-".join(result["code"].split(" ")) + "-" + result["no"]): result["stat"]
            for result in response.json()["results"]
        }

def poll_path_at_penn():
    start_time = time.monotonic()
    with app.app_context():
        from app import get_db # this is hacky, but prevents errors with being outside an app ctx
        for course in course_list:
            statuses = status_on_path_at_penn(
                course
            )
            timestamp = time.monotonic()
            get_db().executemany(
                """
                INSERT INTO path_at_penn_polling(timestamp,semester,section_full_code,status) VALUES (?,?,?,?)
                """,
                [(timestamp, PATH_AT_PENN_SEMESTER, section_code, status) for section_code, status in statuses.items()]
            )
            get_db().commit()
    end_time = time.monotonic()
    logger.info(f"polled {len(course_list)} course statuses in {start_time - end_time} seconds")

if __name__ == "__main__":
    poll_path_at_penn()
