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
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
from static.backend.common_utils import get_next_filename
from static.backend.db_connection import fetch_user_instagram_credentials


POST_CONTAINER_XPATH = (
    "//div[@style[contains(., 'display: flex') and contains(., 'flex-direction: column') "
    "and contains(., 'position: relative')]]"
)


def human_pause(min_seconds=0.2, max_seconds=0.6):
    time.sleep(random.uniform(min_seconds, max_seconds))


def wait_for_document_ready(driver, timeout=10):
    WebDriverWait(driver, timeout).until(
        lambda current_driver: current_driver.execute_script("return document.readyState") == "complete"
    )


def wait_for_any_element(driver, selectors, timeout=10):
    def _find(current_driver):
        for by, value in selectors:
            try:
                elements = current_driver.find_elements(by, value)
                for element in elements:
                    try:
                        if element.is_displayed():
                            return element
                    except StaleElementReferenceException:
                        continue
            except StaleElementReferenceException:
                continue
        return False

    return WebDriverWait(driver, timeout).until(_find)


def wait_for_profile_content(driver, timeout=12):
    wait_for_document_ready(driver, timeout=timeout)
    selectors = [
        (By.XPATH, "//header"),
        (By.XPATH, POST_CONTAINER_XPATH),
        (By.TAG_NAME, "article"),
    ]
    return wait_for_any_element(driver, selectors, timeout=timeout)


def wait_for_post_content(driver, timeout=12):
    wait_for_document_ready(driver, timeout=timeout)
    selectors = [
        (By.XPATH, "//article"),
        (By.XPATH, "//main//time[@datetime]"),
        (By.XPATH, "//div[@role='dialog']"),
    ]
    return wait_for_any_element(driver, selectors, timeout=timeout)


def wait_for_comment_surface(driver, timeout=8):
    selectors = [
        (By.XPATH, "//div[@role='dialog']"),
        (By.XPATH, "//time[@datetime]"),
        (By.XPATH, "//div[@role='button' and @aria-label='Close']"),
    ]
    try:
        return wait_for_any_element(driver, selectors, timeout=timeout)
    except TimeoutException:
        return None


def retry_on_stale(action, description, retries=2, wait_range=(1.2, 2.4)):
    for attempt in range(retries + 1):
        try:
            return action()
        except StaleElementReferenceException as e:
            if attempt == retries:
                raise
            print(f"[WARN] Stale element during {description}. Retrying ({attempt + 1}/{retries})...")
            human_pause(*wait_range)
    return None


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
    username_selectors = [
        (By.NAME, "username"),
        (By.NAME, "email"),
        (By.CSS_SELECTOR, "form input[autocomplete*='username']"),
        (By.CSS_SELECTOR, "form input[type='text']"),
    ]
    password_selectors = [
        (By.NAME, "password"),
        (By.NAME, "pass"),
        (By.CSS_SELECTOR, "form input[type='password']"),
    ]
    submit_selectors = [
        (By.CSS_SELECTOR, "form#login_form button[type='submit']"),
        (By.CSS_SELECTOR, "form#login_form input[type='submit']"),
        (By.XPATH, "//form[@id='login_form']//div[@role='button' and (@aria-label='Log In' or .//span[normalize-space()='Log in'])]"),
        (By.XPATH, "//button[@type='submit']"),
        (By.XPATH, "//div[@role='button' and (@aria-label='Log In' or .//span[normalize-space()='Log in'])]"),
        (By.XPATH, "//span[normalize-space()='Log in']/ancestor::*[@role='button' or self::button][1]"),
    ]

    def wait_for_visible(selectors, timeout=20):
        def _find(current_driver):
            for by, value in selectors:
                elements = current_driver.find_elements(by, value)
                for element in elements:
                    if element.is_displayed():
                        return element
            return False

        return WebDriverWait(driver, timeout).until(_find)

    def find_first_displayed(selectors):
        for by, value in selectors:
            elements = driver.find_elements(by, value)
            for element in elements:
                if element.is_displayed():
                    return element
        return None

    def wait_for_login_transition(timeout=10):
        WebDriverWait(driver, timeout).until(
            lambda current_driver: "accounts/login" not in current_driver.current_url
            or current_driver.find_elements(By.NAME, "verificationCode")
            or current_driver.find_elements(By.CSS_SELECTOR, "input[name='verificationCode']")
        )

    try:
        driver.get("https://www.instagram.com/accounts/login/")
        wait_for_document_ready(driver, timeout=12)
        human_pause(0.6, 1.2)
        i = 0
        while "login" in str.lower(f"{driver.current_url}") and i <= 3:
            i += 1
            print(f"[INFO] Login attempt {i}. Current URL: {driver.current_url}")
            username_field = wait_for_visible(username_selectors, timeout=20)
            password_field = wait_for_visible(password_selectors, timeout=20)

            username_field.clear()
            password_field.clear()
            username_field.send_keys(username)
            password_field.send_keys(password)
            print("login and pass should appear, look for log in button")
            password_field.send_keys(Keys.ENTER)

            try:
                wait_for_login_transition(timeout=10)
                continue
            except TimeoutException:
                print("[INFO] Enter submit did not leave the login page. Trying button click.")

            human_pause(0.4, 0.9)
            login_button = find_first_displayed(submit_selectors)
            if login_button is None:
                raise TimeoutException("Could not locate a visible login submit control.")

            print("must have located log in button")
            form = None
            try:
                form = login_button.find_element(By.XPATH, "ancestor::form[1]")
            except Exception:
                form = None

            if form is not None:
                try:
                    driver.execute_script("arguments[0].requestSubmit();", form)
                except Exception:
                    try:
                        driver.execute_script("arguments[0].submit();", form)
                    except Exception:
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", login_button)
                        try:
                            login_button.click()
                        except Exception:
                            driver.execute_script("arguments[0].click();", login_button)
            else:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", login_button)
                try:
                    login_button.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", login_button)

            wait_for_login_transition(timeout=10)
        if "accounts/login" in driver.current_url:
            print("[WARN] Login failed or still on login page.")
            return False
        else:
            print("[INFO] Login successful.")
            return True
    except Exception as e:
        print(
            f"[ERROR] Instagram login error ({type(e).__name__}): {e!r}. "
            f"URL={driver.current_url}, title={driver.title!r}"
        )
        return False


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
    retry_on_stale(
        lambda: wait_for_comment_surface(driver, timeout=8),
        "waiting for comment surface",
    )
    human_pause(0.3, 0.8)
    retry_on_stale(lambda: try_press_cancel_button(driver), "closing overlay")
    human_pause(0.2, 0.6)
    if retry_on_stale(lambda: click_view_all_comments(driver), "opening all comments"):
        retry_on_stale(
            lambda: wait_for_comment_surface(driver, timeout=8),
            "waiting for expanded comments",
        )
        human_pause(0.25, 0.7)
        retry_on_stale(lambda: click_more_button(driver), "clicking more comments")
        human_pause(0.2, 0.6)
        scroll_container = find_scroll_element_by_scroll_properties(driver, "div")
        if not scroll_container:
            print("[WARN] No scrollable comment containers found.")
        else:
            while True:
                try:
                    if not try_scroll_page(driver, scroll_container):
                        break
                    human_pause(0.15, 0.4)
                except Exception as e:
                    print(f"[ERROR] Error while loading comments: {e}")
                    break
        print("[INFO] All comments loaded.")
    else:
        human_pause(0.2, 0.6)
        if retry_on_stale(lambda: click_reels_comment_button(driver), "opening reels comments"):
            retry_on_stale(
                lambda: wait_for_comment_surface(driver, timeout=8),
                "waiting for reels comments",
            )
            human_pause(0.25, 0.7)
            retry_on_stale(lambda: click_more_button(driver), "clicking more comments")
            human_pause(0.2, 0.6)
        scroll_container = find_scroll_element_by_scroll_properties(driver, "div")
        print("[INFO] Fallback scrolling mode.")
        if not scroll_container:
            print("[WARN] No scrollable comment containers found.")
        else:
            while True:
                try:
                    if not try_scroll_page(driver, scroll_container):
                        break
                    human_pause(0.15, 0.4)
                except Exception as e:
                    print(f"[ERROR] Error while loading comments: {e}")
                    break
        print("[INFO] All comments loaded.")


def get_scroll_wait_profile(driver, scroll_container):
    container_height = driver.execute_script(
        """
        return Math.max(
            arguments[0].clientHeight || 0,
            arguments[0].offsetHeight || 0,
            1
        );
        """,
        scroll_container
    )
    load_timeout = min(3.2, max(1.2, container_height / 550))
    poll_interval = min(0.45, max(0.2, container_height / 4000))
    settle_delay = min(1.4, max(0.45, container_height / 1800))
    return container_height, load_timeout, poll_interval, settle_delay


def try_scroll_page(driver, scroll_container, limit_scrolling=False, stop_scroll_callback=None):
    try:
        _, load_timeout, poll_interval, settle_delay = get_scroll_wait_profile(driver, scroll_container)
        time.sleep(random.uniform(0.6, 1.1))
        time.sleep(random.uniform(0.4, 0.9))
        last_height = driver.execute_script("return arguments[0].scrollHeight", scroll_container)
        time.sleep(random.uniform(0.4, 0.9))
        i = 0
        if stop_scroll_callback and stop_scroll_callback():
            return False
        while True:
            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", scroll_container)
            wait_started = time.time()
            new_height = last_height

            while (time.time() - wait_started) < random.uniform(load_timeout * 0.9, load_timeout * 1.1):
                time.sleep(random.uniform(poll_interval * 0.8, poll_interval * 1.2))
                time.sleep(random.uniform(1.4, 1.9))
                if stop_scroll_callback and stop_scroll_callback():
                    return False
                new_height = driver.execute_script("return arguments[0].scrollHeight", scroll_container)
                if new_height > last_height:
                    growth = new_height - last_height
                    extra_pause = min(1.6, settle_delay + (growth / 2500))
                    time.sleep(random.uniform(extra_pause * 0.7, extra_pause * 1.2))
                    break

            i += 1
            if new_height == last_height:
                return False
            last_height = new_height
            time.sleep(random.uniform(0.35, 0.75))
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
        view_all_comments_xpath = (
            "//a[.//span["
            "contains(normalize-space(), 'View all') "
            "or starts-with(normalize-space(), 'View ')"
            "]]"
        )
        view_all_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, view_all_comments_xpath))
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


def save_comments(driver, POST_URL, target_page, page_name):
    print("[INFO] Opening post...")
    driver.get(POST_URL)
    wait_for_post_content(driver, timeout=12)
    human_pause(0.4, 1.0)
    retry_on_stale(lambda: try_press_cancel_button(driver), "closing overlay")
    print("[INFO] Loading comments...")
    scroll_and_load_comments(driver)

    print("[INFO] Collecting comments...")
    comments_data = collect_comments_and_likes(driver)
    print(comments_data)
    print(f"[INFO] Collected {len(comments_data)} comments. Saving CSV...")
    df = pd.DataFrame(comments_data, columns=["Comment", "Time", "Likes"])
    df.insert(0, "PostHref", POST_URL)
    df.insert(0, "PageID", target_page)
    df.insert(0, "PageName", page_name)
    print(f"df: {df}")
    output_path = get_next_filename(target_page, "unprocessed_data/comments1")
    df.to_csv(output_path, index=False, encoding="utf-8-sig")

    print(f"[INFO] Saved CSV: {output_path}")
    return {
        "output_path": output_path,
        "comments_collected": len(comments_data),
        "post_url": POST_URL,
    }


def find_scroll_elements_by_scroll_properties(driver, element_owner):
    wait_for_document_ready(driver, timeout=8)
    human_pause(0.15, 0.4)
    try_press_cancel_button(driver)
    human_pause(0.15, 0.4)
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


def collect_all_hrefs(container_element, target_page, number_of_posts, href_buffer=None, seen_hrefs=None, skip_hrefs=None):
    hrefs = href_buffer if href_buffer is not None else []
    known_hrefs = seen_hrefs if seen_hrefs is not None else set(hrefs)
    ignored_hrefs = skip_hrefs if skip_hrefs is not None else set()
    try:
        anchor_elements = container_element.find_elements(By.TAG_NAME, "a")
        for anchor in anchor_elements:
            href = anchor.get_attribute("href")
            if href:
                normalized_href = href.replace(f"/{target_page}", "")
                if normalized_href in ignored_hrefs:
                    continue
                if normalized_href not in known_hrefs:
                    known_hrefs.add(normalized_href)
                    hrefs.append(normalized_href)
        print(f"[INFO] Collected {len(hrefs)} post links.")
        return hrefs[0:number_of_posts]
    except Exception as e:
        print(f"[ERROR] Link collection error: {e}")


def get_page_name(driver):
    xpaths = [
        "//header//h2//span[@dir='auto']",
        "//header//div//span[@dir='auto']",
        "//div[contains(@class,'x1q0g3np')]//span[@dir='auto']",
    ]
    for xp in xpaths:
        try:
            elem = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, xp))
            )
            text = elem.text.strip()
            if text:
                return text
        except Exception:
            continue
    return None


def load_all_posts(driver, target_page, number_of_posts, existing_post_hrefs=None):
    driver.get(f"https://www.instagram.com/{target_page}/")
    wait_for_profile_content(driver, timeout=12)
    human_pause(0.4, 0.9)
    page_name = get_page_name(driver) or target_page
    human_pause(0.15, 0.4)
    scroll_container = find_scroll_element_by_scroll_properties(driver, "html")
    human_pause(0.15, 0.4)
    hrefs = []
    seen_hrefs = set()
    skip_hrefs = set(existing_post_hrefs or [])
    reached_post_limit = False

    def refresh_hrefs_and_check_limit():
        nonlocal hrefs, reached_post_limit
        container_element = driver.find_element(
            By.XPATH,
            POST_CONTAINER_XPATH
        )
        hrefs = collect_all_hrefs(
            container_element,
            target_page,
            number_of_posts,
            href_buffer=hrefs,
            seen_hrefs=seen_hrefs,
            skip_hrefs=skip_hrefs,
        )
        if len(hrefs) >= number_of_posts:
            reached_post_limit = True
            print(f"[INFO] Reached requested number of posts: {number_of_posts}.")
            return True
        return False

    while True:
        try:
            if refresh_hrefs_and_check_limit():
                break

            if not try_scroll_page(
                driver,
                scroll_container,
                limit_scrolling=True,
                stop_scroll_callback=refresh_hrefs_and_check_limit,
            ):
                if not reached_post_limit:
                    print("[INFO] All posts loaded.")
                break
            human_pause(0.15, 0.4)
        except Exception as e:
            print(f"[ERROR] Post loading error: {e}")
            break
    return hrefs, page_name


def extract_data(USERNAME, PASSWORD, target_page, number_of_posts, existing_post_hrefs=None):
    delete_previos_files()
    user_agent = UserAgent()
    log = ""
    posts_requested = int(number_of_posts)
    new_posts_found = 0
    posts_loaded = 0
    collected_comment_rows = 0
    saved_files = []
    existing_post_hrefs = set(existing_post_hrefs or [])
    driver = setup_driver(user_agent)
    human_pause(0.4, 0.9)
    driver.refresh()
    wait_for_document_ready(driver, timeout=10)
    human_pause(0.4, 0.9)

    try:
        print("[INFO] Opening Instagram...\n")
        log += "[INFO] Opening Instagram...\n"  # Add log message
        driver.get("https://www.instagram.com/")
        wait_for_document_ready(driver, timeout=12)
        human_pause(0.4, 0.9)
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
        if existing_post_hrefs:
            print(f"[INFO] Found {len(existing_post_hrefs)} existing post hrefs in DB for {target_page}.")
            log += f"[INFO] Found {len(existing_post_hrefs)} existing post hrefs in DB for {target_page}.\n"
        if load_cookie_success:
            posts, page_name = load_all_posts(
                driver,
                target_page,
                number_of_posts,
                existing_post_hrefs=existing_post_hrefs,
            )
            new_posts_found = len(posts)
            for i in posts:
                try:
                    result = save_comments(driver, i, target_page, page_name)
                    posts_loaded += 1
                    collected_comment_rows += result["comments_collected"]
                    saved_files.append(result["output_path"])
                except Exception as e:
                    print(f"[WARN] Skipping post after retries failed: {i}. Reason: {e}")
                    log += f"[WARN] Skipping post after retries failed: {i}. Reason: {e}\n"
        else:
            login_success = login_to_instagram(driver, USERNAME, PASSWORD)
            if login_success:
                save_cookies(driver)
                posts, page_name = load_all_posts(
                    driver,
                    target_page,
                    number_of_posts,
                    existing_post_hrefs=existing_post_hrefs,
                )
                new_posts_found = len(posts)
                for i in posts:
                    try:
                        result = save_comments(driver, i, target_page, page_name)
                        posts_loaded += 1
                        collected_comment_rows += result["comments_collected"]
                        saved_files.append(result["output_path"])
                    except Exception as e:
                        print(f"[WARN] Skipping post after retries failed: {i}. Reason: {e}")
                        log += f"[WARN] Skipping post after retries failed: {i}. Reason: {e}\n"
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

    return {
        "log": log,
        "target_page": target_page,
        "posts_requested": posts_requested,
        "new_posts_found": new_posts_found,
        "posts_loaded": posts_loaded,
        "comments_collected": collected_comment_rows,
        "saved_files": saved_files,
    }


if __name__ == "__main__":
    app_username = os.getenv("APP_USERNAME")
    target_page = os.getenv("TARGET_PAGE")
    number_of_posts = os.getenv("NUMBER_OF_POSTS", "2")

    if not app_username or not target_page:
        raise ValueError("Set APP_USERNAME and TARGET_PAGE environment variables before running extract_data.py directly.")

    instagram_credentials = fetch_user_instagram_credentials(app_username)
    if not instagram_credentials:
        raise ValueError(f"No stored Instagram credentials found for user '{app_username}'.")

    instagram_username = instagram_credentials.get("instagram_login")
    instagram_password = instagram_credentials.get("instagram_password")
    if not instagram_username or not instagram_password:
        raise ValueError(f"Stored Instagram credentials are incomplete for user '{app_username}'.")

    extract_data(instagram_username, instagram_password, target_page, int(number_of_posts))
