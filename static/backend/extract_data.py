import os
import shutil
import time
import random
import pickle
import pandas as pd
from fake_useragent import UserAgent
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException
from static.backend.common_utils import get_next_filename


def delete_previos_files():
    relative_directory = 'unprocessed_data'

    if not os.path.exists(relative_directory):
        os.makedirs(relative_directory, exist_ok=True)
        return

    for filename in os.listdir(relative_directory):
        file_path = os.path.join(relative_directory, filename)

        if os.path.isfile(file_path):
            try:
                os.remove(file_path)
                print(f"Deleted file: {file_path}")
            except Exception as e:
                print(f"Error deleting file {file_path}: {e}")
        elif os.path.isdir(file_path):
            try:
                shutil.rmtree(file_path)
                print(f"Deleted directory: {file_path}")
            except Exception as e:
                print(f"Error deleting directory {file_path}: {e}")


def setup_driver(user_agent):
    options = Options()
    options.add_argument(f"user-agent={user_agent.random}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-notifications")
    options.add_argument("--lang=en")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-sync")
    options.add_argument("--disable-default-apps")
    options.add_argument("--disable-component-update")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-logging")
    options.add_argument("--log-level=3")
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    # options.add_argument("--headless")

    driver_path = os.getenv("CHROMEDRIVER_PATH")
    if driver_path:
        driver = webdriver.Chrome(service=Service(driver_path), options=options)
    else:
        driver = webdriver.Chrome(options=options)

    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            Object.defineProperty(navigator, 'webdriver', {
              get: () => undefined
            })
        """
    })
    return driver


def login_to_instagram(driver, username, password):
    """
       Instagram.
    """
    try:
        driver.get("https://www.instagram.com/accounts/login/")
        time.sleep(random.uniform(3, 5))
        i = 0
        while "login" in str.lower(f"{driver.current_url}") and i <= 3:
            i += 1
            username_field = driver.find_element(By.NAME, "username")
            password_field = driver.find_element(By.NAME, "password")

            username_field.send_keys(username)
            password_field.send_keys(password)
            print("login and pass should appear, look for log in button")
            time.sleep(random.uniform(3, 5))
            time.sleep(10)
            login_button = driver.find_element(By.XPATH, "//span[contains(text(), 'Log in')]")
            print("must have located log in button")
            time.sleep(random.uniform(3, 5))
            login_button.click()

            time.sleep(random.uniform(5, 7))
        if "accounts/login" in driver.current_url:
            print("[WARN] Login failed or still on login page.")
        else:
            print("[INFO] Login successful.")
    except Exception as e:
        print(f"[ERROR] Instagram login error: {e}")


def save_cookies(driver, filename="cookie/cookies.pkl"):
    """
     cookies  .
    """
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "wb") as file:
        pickle.dump(driver.get_cookies(), file)
    print("[INFO] Cookies saved.")


def load_cookies(driver, filename=r"cookie/cookies.pkl"):
    """
     cookies  .
    """
    try:
        if not os.path.exists(filename):
            print("[INFO] Cookies file not found. Proceeding with fresh login.")
            return False

        if os.path.getsize(filename) == 0:
            print("[INFO] Cookies file is empty. Proceeding with fresh login.")
            return False

        with open(filename, "rb") as file:
            cookies = pickle.load(file)

        if not cookies:
            print("[INFO] Cookies file has no data. Proceeding with fresh login.")
            return False

        for cookie in cookies:
            try:
                driver.add_cookie(cookie)
            except Exception as e:
                print(f"[WARN] Failed to add cookie {cookie}: {e}")
                return False

        print("[INFO] Cookies loaded.")
        return True

    except FileNotFoundError:
        print("[INFO] Cookies file not found. Proceeding with fresh login.")
        return False

    except pickle.UnpicklingError:
        print("[WARN] Cookies file is invalid or corrupted. Proceeding with fresh login.")
        return False

    except Exception as e:
        print(f"[ERROR] Cookies error: {e}")
        return False


def scroll_and_load_comments(driver):
    print("[INFO] Loading comments...")
    time.sleep(random.uniform(3, 5))
    try_press_cancel_button(driver)
    time.sleep(random.uniform(3, 5))
    if click_view_all_comments(driver):
        time.sleep(random.uniform(3, 5))
        click_more_button(driver)
        time.sleep(random.uniform(3, 5))
        scroll_container = find_scroll_element_by_scroll_properties(driver, "div")
        if not scroll_container:
            print("[WARN] No scrollable comment containers found.")
        else:
            while True:
                try:
                    if not try_scroll_page(driver, scroll_container):
                        break
                    time.sleep(random.uniform(2, 4))
                except Exception as e:
                    print(f"[ERROR] Error while loading comments: {e}")
                    break
        print("[INFO] All comments loaded.")
    else:
        time.sleep(random.uniform(3, 5))
        if click_reels_comment_button(driver):
            time.sleep(random.uniform(3, 5))
            click_more_button(driver)
            time.sleep(random.uniform(3, 5))
        scroll_container = find_scroll_element_by_scroll_properties(driver, "div")
        print("[INFO] Fallback scrolling mode.")
        if not scroll_container:
            print("[WARN] No scrollable comment containers found.")
        else:
            while True:
                try:
                    if not try_scroll_page(driver, scroll_container):
                        break
                    time.sleep(random.uniform(2, 4))
                except Exception as e:
                    print(f"[ERROR] Error while loading comments: {e}")
                    break
        print("[INFO] All comments loaded.")


def try_scroll_page(driver, scroll_container, limit_scrolling=False):
    time.sleep(random.uniform(3.5, 5.5))
    try:
        last_height = driver.execute_script("return arguments[0].scrollHeight", scroll_container)
        time.sleep(random.uniform(3.5, 5.5))
        i = 0
        while True:
            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", scroll_container)
            time.sleep(random.uniform(3.5, 5.5))
            new_height = driver.execute_script("return arguments[0].scrollHeight", scroll_container)
            i += 1
            if new_height == last_height:
                return False
            last_height = new_height
            if i >= 10 and limit_scrolling:
                return False
    except Exception as e:
        print(f"[ERROR] Scroll error: {e}")
        return False

def collect_comments_and_likes(driver):
    """
    Collect comments (text + likes) and attach times by index from the <time> list.
    """
    import re
    from selenium.webdriver.common.by import By

    def parse_like_text(text):
        if not text:
            return 0
        match = re.search(r"(\d[\d,]*)", text)
        if match:
            return int(match.group(1).replace(",", ""))
        if "like" in text.lower():
            return 1
        return 0

    def max_like_from_texts(texts):
        counts = [parse_like_text(t) for t in texts if t]
        return max(counts) if counts else 0
    
    def pick_container(seed_elem):
        container_xpaths = [
            "ancestor::div[.//time[@datetime] and .//span[contains(translate(., 'LIKE', 'like'), 'like')]][1]",
            "ancestor::div[.//time[@datetime] and .//span[normalize-space()='Reply']][1]",
            "ancestor::div[.//time[@datetime]][1]",
            "ancestor::li[1]",
            "ancestor::div[@role='listitem'][1]",
            "..",
        ]
        for cx in container_xpaths:
            try:
                container = seed_elem.find_element(By.XPATH, cx)
                if container:
                    return container
            except Exception:
                continue
        return seed_elem

    combined_data = []
    seen = set()
    try:
        def add_record(comment_text, time_val, likes_span):
            key = (comment_text, time_val)
            if key in seen:
                return
            seen.add(key)
            combined_data.append({
                "comment": comment_text,
                "time": time_val,
                "likes": likes_span,
            })

        comment_xpath = ".//div[@style='display: inline;']/span[@dir='auto']"
        comment_elements = driver.find_elements(By.XPATH, comment_xpath)

        for elem in comment_elements:
            try:
                comment_text = elem.text.strip()
                if not comment_text:
                    continue

                container = pick_container(elem)

                span_texts = []
                for span in container.find_elements(By.XPATH, ".//span"):
                    t = span.text.strip()
                    if "like" in t.lower():
                        span_texts.append(t)

                likes_span = max_like_from_texts(span_texts)

                time_val = None
                try:
                    time_val = container.find_element(By.XPATH, ".//time[@datetime]").get_attribute("datetime")
                except Exception:
                    time_val = None

                add_record(comment_text, time_val, likes_span)
            except Exception as e:
                print(f"[ERROR] Comment parse failed: {e}")

        if not combined_data:
            time_elements = driver.find_elements(By.XPATH, "//time[@datetime]")
            for time_elem in time_elements:
                try:
                    container = pick_container(time_elem)
                    comment_text = ""

                    try:
                        time_block = time_elem.find_element(By.XPATH, "ancestor::div[.//time[@datetime]][1]")
                        comment_blocks = time_block.find_elements(
                            By.XPATH,
                            "following-sibling::div[.//span[@dir='auto']][1]"
                        )
                        if comment_blocks:
                            comment_text = comment_blocks[0].text.strip()
                    except Exception:
                        comment_text = ""

                    if not comment_text:
                        continue

                    span_texts = []
                    for span in container.find_elements(By.XPATH, ".//span"):
                        t = span.text.strip()
                        if "like" in t.lower():
                            span_texts.append(t)

                    likes_span = max_like_from_texts(span_texts)

                    time_val = time_elem.get_attribute("datetime")
                    add_record(comment_text, time_val, likes_span)
                except Exception:
                    continue

        if any(d["time"] is None for d in combined_data):
            time_elements = driver.find_elements(By.XPATH, "//time[@datetime]")
            times = [t.get_attribute("datetime") for t in time_elements]
            ti = 0
            for d in combined_data:
                if d["time"] is None and ti < len(times):
                    d["time"] = times[ti]
                    ti += 1

        return [
            (d["comment"], d["time"], d["likes"])
            for d in combined_data
        ]

    except Exception as e:
        print(f"[ERROR] Collect failed: {e}")
        return [
            (d["comment"], d["time"], d["likes"])
            for d in combined_data
        ]



def try_press_cancel_button(driver):
    try:
        close_button = driver.find_element(By.XPATH, "//div[@role='button' and @aria-label='Close']")
        close_button.click()
        print("[INFO] Close button clicked.")
    except Exception:
        pass


def click_view_all_comments(driver):
    """
        "View all comments".
    """
    try:
        view_all_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//a[.//span[contains(text(), 'View all')]]"))
        )
        view_all_button.click()
        print("[INFO] Clicked 'View all comments'.")
        return True
    except Exception:
        print("[INFO] 'View all comments' not found.")
        return False


def click_reels_comment_button(driver):
    """
    Reels can hide comments behind a comment button (speech bubble icon).
    Try to locate and click it when "View all comments" is absent.
    """
    try:
        xpaths = [
            "//div[@role='button'][.//svg[@aria-label='Comment']]",
            "//div[@role='button'][.//title[normalize-space()='Comment']]",
            "//svg[@aria-label='Comment']/ancestor::div[@role='button'][1]",
            "//title[normalize-space()='Comment']/ancestor::div[@role='button'][1]",
        ]

        for xp in xpaths:
            try:
                comment_button = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, xp))
                )
                comment_button.click()
                print("[INFO] Clicked comment button (reels).")
                return True
            except Exception:
                continue

        for xp in xpaths:
            try:
                elems = driver.find_elements(By.XPATH, xp)
                if elems:
                    elems[0].click()
                    print("[INFO] Clicked comment button (reels).")
                    return True
            except Exception:
                continue

        print("[INFO] Comment button (reels) not found.")
        return False
    except Exception:
        print("[INFO] Comment button (reels) not found.")
        return False


def click_more_button(driver):
    """
        'more'  .
    """
    try:
        more_button_xpath = "//div[@aria-disabled='false' and @role='button' and @style='cursor: pointer; display: inline-block;']//span[text()='more']"

        more_button = driver.find_element(By.XPATH, more_button_xpath)
        print("[INFO] Found 'more' button, clicking...")

        more_button.click()
        print("[INFO] Clicked 'more' button.")

        return True
    except NoSuchElementException:
        print("[INFO] 'more' button not found.")
        return False
    except Exception as e:
        print(f"[ERROR] Error clicking 'more': {e}")
        return False


def save_comments(driver, POST_URL, target_page):
    print("[INFO] Opening post...")
    driver.get(POST_URL)
    time.sleep(random.uniform(5, 7))
    try_press_cancel_button(driver)
    print("[INFO] Loading comments...")
    scroll_and_load_comments(driver)

    print("[INFO] Collecting comments...")
    comments_data = collect_comments_and_likes(driver)
    print(comments_data)
    print(f"[INFO] Collected {len(comments_data)} comments. Saving CSV...")
    df = pd.DataFrame(comments_data, columns=["Comment", "Time", "Likes"])
    print(f"df: {df}")
    output_path = get_next_filename(target_page, "unprocessed_data/comments1")
    df.to_csv(output_path, index=False, encoding="utf-8-sig")

    print(f"[INFO] Saved CSV: {output_path}")


def find_scroll_elements_by_scroll_properties(driver, element_owner):
    time.sleep(random.uniform(2, 4))
    try_press_cancel_button(driver)
    time.sleep(random.uniform(2, 4))
    try:
        elements = driver.find_elements(By.TAG_NAME, element_owner)
        candidates = []
        for elem in elements:
            try:
                scroll_height = driver.execute_script("return arguments[0].scrollHeight;", elem)
                client_height = driver.execute_script("return arguments[0].clientHeight;", elem)
                potential = scroll_height - client_height
                if potential > 0:
                    candidates.append((potential, elem))
            except Exception:
                continue

        candidates.sort(key=lambda x: x[0], reverse=True)
        if candidates:
            print(f"[INFO] Found {len(candidates)} scrollable containers. Using the largest first.")
            return [elem for _, elem in candidates]

        print("[WARN] Scrollable container not found.")
        return []
    except Exception as e:
        print(f"[ERROR] Scrollable container search error: {e}")
        return []


def find_scroll_element_by_scroll_properties(driver, element_owner):
    containers = find_scroll_elements_by_scroll_properties(driver, element_owner)
    return containers[0] if containers else None


def collect_all_hrefs(container_element, target_page, number_of_posts):
    hrefs = []
    try:
        anchor_elements = container_element.find_elements(By.TAG_NAME, "a")
        for anchor in anchor_elements:
            href = anchor.get_attribute("href")
            if href:
                hrefs.append(href.replace(f"/{target_page}", ""))
        print(f"[INFO] Collected {len(hrefs)} post links.")
        return list(reversed(hrefs))[0:number_of_posts]
    except Exception as e:
        print(f"[ERROR] Link collection error: {e}")


def load_all_posts(driver, target_page, number_of_posts):
    time.sleep(random.uniform(2, 4))
    driver.get(f"https://www.instagram.com/{target_page}/")
    time.sleep(random.uniform(2, 4))
    scroll_container = find_scroll_element_by_scroll_properties(driver, "html")
    time.sleep(random.uniform(2, 4))
    while True:
        try:
            if not try_scroll_page(driver, scroll_container, limit_scrolling=True):
                print("[INFO] All posts loaded.")
                break
            time.sleep(random.uniform(2, 4))
        except Exception as e:
            print(f"[ERROR] Post loading error: {e}")
            break
    container_element = driver.find_element(By.XPATH,
                                            "//div[@style[contains(., 'display: flex') and contains(., 'flex-direction: column') and contains(., 'position: relative')]]")
    return collect_all_hrefs(container_element, target_page, number_of_posts)


def extract_data(USERNAME, PASSWORD, target_page, number_of_posts):
    delete_previos_files()
    user_agent = UserAgent()
    log = ""
    driver = setup_driver(user_agent)
    time.sleep(random.uniform(3, 5))
    driver.refresh()
    time.sleep(random.uniform(3, 5))

    try:
        print("[INFO] Opening Instagram...\n")
        log += "[INFO] Opening Instagram...\n"  # Add log message
        driver.get("https://www.instagram.com/")
        time.sleep(random.uniform(3, 5))
        print("[INFO] Loading cookies...\n")
        log += "[INFO] Loading cookies...\n"  # Add log message
        load_cookie_success = load_cookies(driver)
        if load_cookie_success:
            print("[INFO] Cookies loaded successfully.\n")
            log += "[INFO] Cookies loaded successfully.\n"  # Add success log
        else:
            print("[INFO] No valid cookies. Logging in.\n")
            log += "[INFO] No valid cookies. Logging in.\n"  # Add failure log
        print("[INFO] Starting data collection...\n")
        log += "[INFO] Starting data collection...\n"  # Add log message
        if load_cookie_success:
            for i in load_all_posts(driver, target_page, number_of_posts):
                save_comments(driver, i, target_page)
        else:
            login_to_instagram(driver, USERNAME, PASSWORD)
            save_cookies(driver)
            if "/accounts/login/" not in driver.current_url:
                for i in load_all_posts(driver, target_page, number_of_posts):
                    save_comments(driver, i, target_page)
            else:
                print(f"[WARN] Login failed: still at {driver.current_url}\n")
                log += f"[WARN] Login failed: still at {driver.current_url}\n"  # Add failure log
        print("[INFO] Data collection finished.\n")
        log += "[INFO] Data collection finished.\n"  # Add success log
    except Exception as e:
        print(f"[ERROR] Data collection error: {e}\n")
        log += f"[ERROR] Data collection error: {e}\n"  # Add error log

    finally:
        driver.quit()

    return log


if __name__ == "__main__":
    extract_data("dobrogo_scientist", "andrian1233", "hnatiuk_ivan", 2)
    # insert_data_to_database()







