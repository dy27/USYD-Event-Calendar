import datetime
from datetime import timedelta
import pickle
import os.path
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import sys


def calendar_setup():
    """ Google Calendar API Setup """

    # If modifying these scopes, delete the file token.pickle.
    SCOPES = ['https://www.googleapis.com/auth/calendar']

    creds = None
    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server()
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    service = build('calendar', 'v3', credentials=creds)
    return service


def remove_duplicates(service):
    """ Iterates through all calendar events in the past week, and removes duplicates. """

    print("\nRemoving duplicate events:")
    min_time = (datetime.datetime.utcnow()-timedelta(days=7)).isoformat() + 'Z'  # 'Z' indicates UTC time
    events_result = service.events().list(calendarId='primary', timeMin=min_time,
                                          maxResults=2500, singleEvents=True,
                                          orderBy='updated').execute()
    events = events_result.get('items', [])
    print(f"Found {len(events)} upcoming events.")
    facebook_ids = []
    google_ids = []

    if not events:
        print('No upcoming events found.')
    for event in events:
        f_id = event['description'].split("\n")[0].split("/")[-1]
        g_id = event['id']
        if f_id in facebook_ids:
            index = facebook_ids.index(f_id)  # Get the index of the duplicate event ID
            service.events().delete(calendarId='primary', eventId=google_ids[index]).execute()
            print(f"Duplicate found: https://www.facebook.com/events/{f_id}")
            facebook_ids.pop(index)
            google_ids.pop(index)

        facebook_ids.append(f_id)
        google_ids.append(g_id)

    print("Duplicate Events Removed")


def calendar_get(service):
    """ Prints the next 10 upcoming events. """
    now = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time

    print('Getting the upcoming 10 events')
    events_result = service.events().list(calendarId='primary', timeMin=now,
                                          maxResults=10, singleEvents=True,
                                          orderBy='startTime').execute()
    events = events_result.get('items', [])

    if not events:
        print('No upcoming events found.')
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        print(start, event['summary'])


def calendar_insert(service, event_info):
    """ Exports an event to Google Calendar. """
    event = service.events().insert(calendarId='primary', body=event_info).execute()
    print('Event created: %s' % (event.get('htmlLink')))


start = time.time()  # Time program execution

service = calendar_setup()  # Set up the calendar API

if "-remove_duplicates" in sys.argv:
    remove_duplicates(service)
    exit()

chrome_options = webdriver.ChromeOptions()

# Disable browser notifications
prefs = {"profile.default_content_setting_values.notifications": 2}
chrome_options.add_experimental_option("prefs", prefs)

# Disable images
prefs = {"profile.managed_default_content_settings.images": 2}
chrome_options.add_experimental_option("prefs", prefs)

chrome_options.add_argument("--start-maximized")
chrome_options.add_argument("--incognito")

driver = webdriver.Chrome(chrome_options=chrome_options)
driver.set_page_load_timeout("100")


# Convert the .txt file into a list of URLs
with open("event_pages.txt", "r") as file:
    pages = file.readlines()
pages = [x.strip() for x in pages]
print(pages)

if os.path.isfile("page_log.txt") == True:      # If log file exists
    if os.stat("page_log.txt").st_size != 0:    # If log file is not empty
        print("\nThe last session was interrupted.")
        print("Removing the pages completed in the last session:")
        remove_pages = []
        for page in pages:
            with open("page_log.txt", "r") as file:
                for line in file:
                    if line.strip() == page:
                        print(page)
                        remove_pages.append(page)

        for page in remove_pages:
            pages.remove(page)


page_count = 0
for page in pages:
    driver.get(page + "events")
    page_count += 1
    page_name = WebDriverWait(driver, 20).until(EC.visibility_of_element_located((By.ID, "u_0_0"))).text
    print(f"\n{page_name.strip()} ..... Page {page_count} of {len(pages)} ..... Runtime: {int((time.time()-start)/60)} min {round((time.time()-start)%60)} seconds")

    time.sleep(2)

    print("Getting links... ", end="")
    links = driver.find_elements_by_xpath("//a[@href]")  # Get all hyperlinks on the page
    print("{} links found:".format(len(links)))

    new_events = []
    for link in links:
        if "facebook.com/events" in link.get_attribute("href"):
            event = link.get_attribute("href").split("/")[4]  # Get the event ID from the URL
            new_events.append(event)

    print("Number of new events:", len(new_events))

    for event in new_events:

        driver.get("https://www.facebook.com/events/" + event)

        event_info = {}

        event_info["summary"] = WebDriverWait(driver, 20).until(
            EC.visibility_of_element_located((By.ID, "seo_h1_tag"))).text
        print(event_info["summary"].strip(), end="\t\t\t")

        duration = WebDriverWait(driver, 20).until(
            EC.visibility_of_element_located((By.CLASS_NAME, "_2ycp"))).get_attribute("content")
        duration = duration.split()

        event_info["start"] = {"dateTime": duration[0],
                               "timeZone": "Australia/Sydney"}  # MAYBE REMOVE TIMEZONE

        if len(duration) >= 3:
            event_date = duration[2][:10]
            event_info["end"] = {"dateTime": duration[2],
                                 "timeZone": "Australia/Sydney"}
        else:
            event_date = duration[0][:10]  # If no end date specified use the starting event date
            event_info["end"] = event_info["start"]

        if event_date < str(datetime.date.today()):  # If event has finished, skip it
            print("Event has already passed.")
            break   # The following events will also have already passed, so move to next page

        event_info["description"] = f"https://www.facebook.com/events/{event}\n\n"
        event_info["description"] += WebDriverWait(driver, 20).until(EC.visibility_of_element_located((By.CLASS_NAME, "_63ew"))).text

        location_info = driver.find_elements_by_class_name("_5xhk")
        if len(location_info) >= 2: # If location is defined
            event_info["location"] = location_info[1].text

        calendar_insert(service, event_info)

    with open("page_log.txt", "a") as file:
        file.write(page + "\n")

# Clear the session log upon program completion
file = open("page_log.txt", "w")
file.close()

time.sleep(2)
driver.quit()

remove_duplicates(service)  # Remove duplicate events

# Finish timing program execution
end = time.time()
print(f"\nTotal Runtime: {int((end-start)/60)} min {int(round((end-start)%60))} sec")