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
from static.backend.db_connection import insert_data_to_database



def delete_previos_files():
    relative_directory = 'unprocessed_data'  # Replace with your relative directory path

    # List all items in the relative directory
    for filename in os.listdir(relative_directory):
        file_path = os.path.join(relative_directory, filename)

        # Check if it's a file
        if os.path.isfile(file_path):
            try:
                os.remove(file_path)  # Delete the file
                print(f"Deleted file: {file_path}")
            except Exception as e:
                print(f"Error deleting file {file_path}: {e}")
        # Check if it's a directory
        elif os.path.isdir(file_path):
            try:
                shutil.rmtree(file_path)  # Delete the directory and its contents
                print(f"Deleted directory: {file_path}")
            except Exception as e:
                print(f"Error deleting directory {file_path}: {e}")


def get_next_filename(base_filename, folder="unprocessed_data/comments1"):
    """
    Генерує унікальну назву файлу, додаючи +1 до номера.
    """
    if not os.path.exists(folder):
        os.makedirs(folder)

    files = os.listdir(folder)

    matching_files = [f for f in files if f.startswith(base_filename) and f.endswith(".csv")]

    max_number = 0
    for file in matching_files:
        try:
            number = int(file.replace(base_filename, "").replace(".csv", "").strip("_"))
            if number > max_number:
                max_number = number
        except ValueError:
            continue

    next_number = max_number + 1
    return os.path.join(folder, f"{base_filename}_{next_number}.csv")


def setup_driver(user_agent):
    options = Options()
    options.add_argument(f"user-agent={user_agent.random}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-notifications")
    options.add_argument("--lang=en")
    options.add_argument("--start-maximized")
    # режим збирання коментарів без відкритого вікна браузера
    # options.add_argument("--headless")

    driver = webdriver.Chrome(service=Service(r"C:\chromedriver\chromedriver-win64\chromedriver.exe"), options=options)

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
    Виконує авторизацію в Instagram.
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
            print("[❌] Авторизація не виконана. Перевірте логін і пароль.")
        else:
            print("[✅] Авторизація виконана успішно.")
    except Exception as e:
        print(f"[❌] Помилка при вході в Instagram: {e}")


def save_cookies(driver, filename="cookie/cookies.pkl"):
    """
    Зберігає cookies у файл.
    """
    with open(filename, "wb") as file:
        pickle.dump(driver.get_cookies(), file)
    print("[✅] Cookies збережено.")


def load_cookies(driver, filename=r"cookie/cookies.pkl"):
    """
    Завантажує cookies із файлу.
    """
    try:
        if not os.path.exists(filename):
            print("[❌] Cookies файл не існує. Виконуємо новий вхід.")
            return False

        if os.path.getsize(filename) == 0:
            print("[❌] Cookies файл порожній. Виконуємо новий вхід.")
            return False

        with open(filename, "rb") as file:
            cookies = pickle.load(file)

        if not cookies:
            print("[❌] Cookies файл порожній. Виконуємо новий вхід.")
            return False

        for cookie in cookies:
            try:
                driver.add_cookie(cookie)
            except Exception as e:
                print(f"[❌] Помилка додавання cookie: {cookie}, {e}")
                return False

        print("[✅] Cookies завантажено.")
        return True

    except FileNotFoundError:
        print("[❌] Cookies файл не знайдено. Виконуємо новий вхід.")
        return False

    except pickle.UnpicklingError:
        print("[❌] Cookies файл пошкоджений або некоректний. Виконуємо новий вхід.")
        return False

    except Exception as e:
        print(f"[❌] Cookies якась проблема: {e}")
        return False


def scroll_and_load_comments(driver):
    """
    Завантажує всі коментарі за допомогою скролінгу.
    """
    print("[ℹ️] Починаємо завантаження коментарів...")
    time.sleep(random.uniform(3, 5))
    try_press_cancel_button(driver)
    time.sleep(random.uniform(3, 5))
    click_view_all_comments(driver)
    time.sleep(random.uniform(3, 5))
    click_more_button(driver)
    time.sleep(random.uniform(3, 5))
    scroll_container = find_scroll_element_by_scroll_properties(driver, "div")
    while True:
        try:
            if not try_scroll_page(driver, scroll_container):
                print("[ℹ️] Усі коментарі завантажено.")
                break
            time.sleep(random.uniform(2, 4))
        except Exception as e:
            print(f"[❌] Помилка під час завантаження коментарів: {e}")
            break


def try_scroll_page(driver, scroll_container, limit_scrolling=False):
    """
    Скролить область коментарів вниз для завантаження нових коментарів.
    """
    time.sleep(random.uniform(2, 4))
    try:
        last_height = driver.execute_script("return arguments[0].scrollHeight", scroll_container)
        time.sleep(random.uniform(2, 4))
        i = 0
        while True:
            driver.execute_script("arguments[0].scrollTo(0, arguments[0].scrollHeight);", scroll_container)
            time.sleep(random.uniform(2, 4))
            new_height = driver.execute_script("return arguments[0].scrollHeight", scroll_container)
            i += 1
            if new_height == last_height:
                return False
            last_height = new_height
            if i >= 10 and limit_scrolling:
                return False
    except Exception as e:
        print(f"[❌] Помилка під час скролінгу: {e}")
        return False


def collect_comments(driver):
    """
    Збирає всі коментарі зі сторінки.
    """
    comments = []
    try:
        comment_xpath = ".//div[@style='display: inline;']/span[@dir='auto']"

        comment_elements = driver.find_elements(By.XPATH, comment_xpath)
        for elem in comment_elements:
            text = elem.text.strip()
            if text:
                comments.append(text)
        print(f"[✅] Зібрано {len(comments)} коментарів.")
    except Exception as e:
        print(f"[❌] Помилка при зборі коментарів: {e}")
    return comments


def try_press_cancel_button(driver):
    try:
        close_button = driver.find_element(By.XPATH, "//div[@role='button' and @aria-label='Close']")
        close_button.click()
        print("[✅] Close button clicked successfully.")
    except Exception:
        pass


def click_view_all_comments(driver):
    """
    Знаходить і натискає кнопку "View all comments".
    """
    try:
        view_all_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//a[.//span[contains(text(), 'View all')]]"))
        )
        view_all_button.click()
        print("[✅] Кнопка 'View all comments' натиснута.")
    except Exception as e:
        print(f"[❌] Помилка: Кнопка 'View all comments' не знайдена або не натиснута. Деталі: {e}")


def click_more_button(driver):
    """
    Знаходить і натискає кнопку 'more' на сторінці.
    """
    try:
        more_button_xpath = "//div[@aria-disabled='false' and @role='button' and @style='cursor: pointer; display: inline-block;']//span[text()='more']"

        more_button = driver.find_element(By.XPATH, more_button_xpath)
        print("[ℹ️] Кнопка 'more' знайдена. Натискаємо...")

        more_button.click()
        print("[✅] Кнопка 'more' натиснута.")

        return True
    except NoSuchElementException:
        print("[❌] Кнопка 'more' не знайдена.")
        return False
    except Exception as e:
        print(f"[❌] Помилка під час натискання кнопки 'more': {e}")
        return False


def save_comments(driver, POST_URL, target_page):
    print("[🔍] Відкриваємо публікацію...")
    driver.get(POST_URL)
    time.sleep(random.uniform(5, 7))
    try_press_cancel_button(driver)
    print("[⏬] Завантажуємо коментарі...")
    scroll_and_load_comments(driver)

    print("[📥] Збираємо коментарі...")
    comments = collect_comments(driver)

    print(f"[✅] Зібрано {len(comments)} коментарів. Зберігаємо у файл...")
    df = pd.DataFrame(comments, columns=["Comment"])
    df.to_csv(get_next_filename(target_page), index=False, encoding="utf-8-sig")

    print(f"[🎉] Успішно збережено в файл: {get_next_filename(target_page)}")


def find_scroll_element_by_scroll_properties(driver, element_owner):
    """
    Знаходить скролюваний елемент, перевіряючи його властивості.
    """
    time.sleep(random.uniform(2, 4))
    try_press_cancel_button(driver)
    time.sleep(random.uniform(2, 4))
    try:
        div_elements = driver.find_elements(By.TAG_NAME, element_owner)

        for div in div_elements:
            is_scrollable = driver.execute_script(
                "return arguments[0].scrollHeight > arguments[0].clientHeight;", div
            )
            if is_scrollable:
                print("[✅] Знайдено скролюваний елемент.")
                return div

        print("[❌] Скролюваний елемент не знайдено.")
        return None
    except Exception as e:
        print(f"[❌] Помилка під час пошуку скролюваного елемента: {e}")
        return None


def collect_all_hrefs(container_element, target_page, number_of_posts):
    """
    Збирає всі значення href з елементів <a> всередині вказаного контейнера.

    :param container_element: елемент контейнера <div>, в якому потрібно шукати <a>
    :return: список значень href
    """
    hrefs = []
    try:
        anchor_elements = container_element.find_elements(By.TAG_NAME, "a")
        for anchor in anchor_elements:
            href = anchor.get_attribute("href")
            if href:
                hrefs.append(href.replace(f"/{target_page}", ""))
        print(f"[✅] Зібрано {len(hrefs)} посилань.")
        return hrefs[0:number_of_posts]
    except Exception as e:
        print(f"[❌] Помилка при зборі посилань: {e}")


def load_all_posts(driver, target_page, number_of_posts):
    time.sleep(random.uniform(2, 4))
    driver.get(f"https://www.instagram.com/{target_page}/")
    time.sleep(random.uniform(2, 4))
    scroll_container = find_scroll_element_by_scroll_properties(driver, "html")
    time.sleep(random.uniform(2, 4))
    while True:
        try:
            if not try_scroll_page(driver, scroll_container, limit_scrolling=True):
                print("[ℹ️] Усі дописи завантажено.")
                break
            time.sleep(random.uniform(2, 4))
        except Exception as e:
            print(f"[❌] Помилка під час завантаження дописів: {e}")
            break
    container_element = driver.find_element(By.XPATH,
                                            "//div[@style[contains(., 'display: flex') and contains(., 'flex-direction: column') and contains(., 'position: relative')]]")
    return collect_all_hrefs(container_element, target_page, number_of_posts)


def load_data(USERNAME, PASSWORD, target_page, number_of_posts):

    delete_previos_files()
    user_agent = UserAgent()
    log = ""
    driver = setup_driver(user_agent)
    time.sleep(random.uniform(3, 5))
    driver.refresh()
    time.sleep(random.uniform(3, 5))

    try:
        print("[🔍] Відкриваємо Instagram...\n")
        log += "[🔍] Відкриваємо Instagram...\n"  # Add log message
        driver.get("https://www.instagram.com/")
        time.sleep(random.uniform(3, 5))
        print("[🔍] збираємо cookies\n")
        log += "[🔍] збираємо cookies\n"  # Add log message
        load_cookie_success = load_cookies(driver)
        if load_cookie_success:
            print("[✅] успішно використано попередні Cookie\n")
            log += "[✅] успішно використано попередні Cookie\n"  # Add success log
        else:
            print("[❌] не вдалось використати попередні Cookie\n")
            log += "[❌] не вдалось використати попередні Cookie\n"  # Add failure log
        print("[🔍] Виконуємо авторизацію...\n")
        log += "[🔍] Виконуємо авторизацію...\n"  # Add log message
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
                print(f"[❌] ./accounts/login/ in {driver.current_url}\n")
                log += f"[❌] ./accounts/login/ in {driver.current_url}\n"  # Add failure log
        print("[✅] успішно завантажено всі дані\n")
        log += "[✅] успішно завантажено всі дані\n"  # Add success log
    except Exception as e:
        print(f"[❌] Помилка: {e}\n")
        log += f"[❌] Помилка: {e}\n"  # Add error log

    finally:
        driver.quit()

    return log



# load_data("dobrogo_scientist", "andrian1233", "hnatiuk_ivan", 2)


# insert_data_to_database()