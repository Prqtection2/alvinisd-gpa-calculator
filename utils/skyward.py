from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager
import platform
import time
import os
import subprocess
import traceback
import logging
import base64

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def save_screenshot_base64(driver, name):
    try:
        screenshot = driver.get_screenshot_as_base64()
        logger.info(f"Screenshot {name} (base64): {screenshot}")
        return screenshot
    except Exception as e:
        logger.error(f"Failed to take screenshot {name}: {str(e)}")
        return None

class SkywardGPA:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.driver = None
        self.grades_raw = {}
        self.grades = {}
        self.period_gpas = {}
        self.weighted_period_gpas = {}
        self.period_order = ['1U1', '1U2', 'NW1', '2U1', '2U2', 'NW2', 'EX1', 'SM1', 
                            '3U1', '3U2', 'NW3', '4U1', '4U2', 'NW4', 'EX2', 'SM2', 'YR']
        self.ordered_periods = []

    def calculate(self):
        try:
            logger.info("Setting up Chrome options...")
            options = webdriver.ChromeOptions()
            
            if platform.system() == 'Linux':  # Render
                chrome_binary = '/usr/bin/google-chrome'
                logger.info(f"Using Chrome binary: {chrome_binary}")
                options.binary_location = chrome_binary
                
                # Memory optimization arguments
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-dev-shm-usage')
                options.add_argument('--disable-gpu')
                options.add_argument('--headless=new')
                options.add_argument('--disable-extensions')
                options.add_argument('--disable-software-rasterizer')
                options.add_argument('--disable-features=VizDisplayCompositor')
                options.add_argument('--window-size=800,600')  # Smaller window size
                options.add_argument('--disable-javascript')  # Disable JS when possible
                options.add_argument('--blink-settings=imagesEnabled=false')  # Disable images
                options.add_argument('--memory-pressure-off')
            else:  # Local
                options.add_argument('--headless=new')
            
            # Common options
            options.add_argument('--ignore-certificate-errors')
            options.add_experimental_option('excludeSwitches', ['enable-logging'])
            
            logger.info("Initializing Chrome driver...")
            try:
                self.driver = webdriver.Chrome(options=options)
                self.driver.set_page_load_timeout(30)  # Set page load timeout
                self.driver.set_script_timeout(30)     # Set script timeout
                logger.info("Chrome driver initialized successfully")
            except Exception as e:
                logger.error(f"Error initializing Chrome driver: {str(e)}")
                raise

            self.login()
            save_screenshot_base64(self.driver, "after_login")
            self.navigate_to_gradebook()
            self.extract_grades()
            self.calculate_gpas()
            
            return {
                'grades_raw': self.grades_raw,
                'grades': self.grades,
                'unweighted_gpas': self.period_gpas,
                'weighted_gpas': self.weighted_period_gpas,
                'ordered_periods': self.ordered_periods
            }
        except Exception as e:
            logger.error(f"Error in calculate: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            if self.driver:
                save_screenshot_base64(self.driver, "error_state")
            raise
        finally:
            if self.driver:
                try:
                    self.driver.quit()
                except Exception as e:
                    logger.error(f"Error closing driver: {str(e)}")

    def login(self):
        try:
            logger.info("Attempting to access login page...")
            login_url = "https://skyward-alvinprod.iscorp.com/scripts/wsisa.dll/WService=wsedualvinisdtx/fwemnu01.w"
            self.driver.get(login_url)
            
            current_url = self.driver.current_url
            logger.info(f"Current URL before login: {current_url}")
            if "fwemnu01.w" not in current_url:
                logger.error(f"Unexpected URL before login: {current_url}")
                self.driver.get(login_url)
                time.sleep(2)
            
            logger.info("Waiting for username input...")
            username_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, '/html/body/form[1]/div/div/div[4]/div[2]/div[1]/div[2]/div/table/tbody/tr[1]/td[2]/input'))
            )
            username_input.send_keys(self.username)
            logger.info("Username entered successfully")

            password_input = self.driver.find_element(By.XPATH, '/html/body/form[1]/div/div/div[4]/div[2]/div[1]/div[2]/div/table/tbody/tr[2]/td[2]/input')
            password_input.send_keys(self.password)

            sign_in_button = self.driver.find_element(By.XPATH, '/html/body/form[1]/div/div/div[4]/div[2]/div[1]/div[2]/div/table/tbody/tr[7]/td/a')
    sign_in_button.click()

            try:
                WebDriverWait(self.driver, 10).until(lambda d: len(d.window_handles) > 1)
                logger.info("New window detected after login")
            except:
                try:
                    error_element = WebDriverWait(self.driver, 3).until(
                        EC.presence_of_element_located((By.CLASS_NAME, 'validation-error'))
                    )
                    raise Exception("Incorrect username or password. Please check your credentials and try again.")
                except:
                    current_url = self.driver.current_url
                    logger.info(f"Current URL after login attempt: {current_url}")
                    if "sfhome01.w" in current_url:
                        logger.info("Successfully redirected to home page")
                    else:
                        raise Exception("Login failed. Please double-check your password and try again. If you're sure your password is correct, try again in a few minutes.")

        except Exception as e:
            if "Incorrect username or password" in str(e) or "Login failed" in str(e):
                raise e
            raise Exception("Login failed. Please double-check your password and try again. If you're sure your password is correct, try again in a few minutes.")

    def navigate_to_gradebook(self):
        try:
            logger.info("Checking current URL before navigation...")
            current_url = self.driver.current_url
            logger.info(f"Current URL: {current_url}")
            
            if len(self.driver.window_handles) > 1:
                logger.info("Multiple windows detected, switching to new window...")
                self.driver.switch_to.window(self.driver.window_handles[1])
                logger.info("Successfully switched to new window")
            else:
                logger.info("Single window detected, continuing in current window")
            
            logger.info("Looking for gradebook button...")
            gradebook_found = False
            max_attempts = 2
            
            for attempt in range(max_attempts):
                try:
                    logger.info(f"Attempt {attempt + 1} to find gradebook button")
                    
                    # First try direct access to gradebook (expanded menu)
                    try:
                        logger.info("Trying expanded menu layout...")
                        gradebook_button = WebDriverWait(self.driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, '/html/body/div[1]/div[2]/div[2]/div[1]/div/ul[2]/li[3]/a'))
                        )
                        gradebook_button.click()
                        gradebook_found = True
                        logger.info("Found and clicked gradebook in expanded menu")
                        break
                    except Exception as e:
                        logger.info(f"Expanded menu attempt failed: {str(e)}")
                        
                    # If direct access fails, try the collapsed menu approach
                    try:
                        logger.info("Trying collapsed menu layout...")
                        # Click the + button first
                        plus_button = WebDriverWait(self.driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, '/html/body/div[1]/div[2]/div[2]/div[1]/div/ul[1]/li/a'))
                        )
                        plus_button.click()
                        logger.info("Clicked + button successfully")
                        
                        # Wait a moment for the menu to expand
                        time.sleep(1)
                        
                        # Now try to click the gradebook button
                        gradebook_button = WebDriverWait(self.driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, '/html/body/div[1]/div[2]/div[2]/div[1]/div/ul[2]/li[3]/a'))
                        )
                        gradebook_button.click()
                        gradebook_found = True
                        logger.info("Found and clicked gradebook in collapsed menu")
                        break
                    except Exception as e:
                        logger.info(f"Collapsed menu attempt failed: {str(e)}")
                        
                    # If both methods fail, try link text as last resort
                    try:
                        logger.info("Trying link text method...")
                        gradebook_button = WebDriverWait(self.driver, 10).until(
                            EC.element_to_be_clickable((By.LINK_TEXT, "Gradebook"))
                        )
                        gradebook_button.click()
                        gradebook_found = True
                        logger.info("Found and clicked gradebook using link text")
                        break
                    except Exception as e:
                        logger.info(f"Link text attempt failed: {str(e)}")
                        
                except Exception as attempt_error:
                    logger.warning(f"Attempt {attempt + 1} failed: {str(attempt_error)}")
                    if attempt < max_attempts - 1:
                        self.driver.refresh()
                        time.sleep(2)
                    continue
            
            if not gradebook_found:
                raise Exception("Failed to find or click gradebook button after all attempts")
            
            logger.info("Successfully triggered gradebook button click")
            
            logger.info("Waiting for gradebook to load...")
            try:
                WebDriverWait(self.driver, 30).until(
                    EC.presence_of_element_located((By.XPATH, '/html/body/div[1]/div[2]/div[2]/div[2]/div/div[4]/div[4]/div[2]/div[1]/div/div[1]/div[1]/table/thead/tr/th'))
                )
                logger.info("Gradebook loaded successfully")
            except Exception as timeout_error:
                logger.error("Timeout waiting for gradebook to load")
                raise

        except Exception as e:
            logger.error(f"Error in navigate_to_gradebook: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    def extract_grades(self):
        try:
            logger.info("Starting grade extraction...")
            logger.info("Finding grading periods...")
    grading_periods_xpath = '/html/body/div[1]/div[2]/div[2]/div[2]/div/div[4]/div[4]/div[2]/div[1]/div/div[1]/div[1]/table/thead/tr/th'
            grading_periods = self.driver.find_elements(By.XPATH, grading_periods_xpath)
            logger.info(f"Found {len(grading_periods)} grading periods")
    
    period_labels = []
    for period in grading_periods:
        try:
            label = period.get_attribute('innerText')
            if label:
                period_labels.append(label)
            else:
                period_labels.append('-')
                except Exception as e:
                    logger.error(f"Error getting period label: {str(e)}")
            period_labels.append('-')

            logger.info(f"Period labels: {period_labels}")

            self.ordered_periods = [period for period in self.period_order 
                                  if period in period_labels and 'C' not in period]
            logger.info(f"Ordered periods: {self.ordered_periods}")

            logger.info("Finding classes container...")
    classes_container_xpath = '/html/body/div[1]/div[2]/div[2]/div[2]/div/div[4]/div[4]/div[2]/div[2]/div[2]/table/tbody'
            classes_container = self.driver.find_element(By.XPATH, classes_container_xpath)
    class_rows = classes_container.find_elements(By.XPATH, './tr')
            logger.info(f"Found {len(class_rows)} class rows")

            for class_index, class_row in enumerate(class_rows, 1):
        try:
                    logger.info(f"Processing class {class_index}/{len(class_rows)}")
            class_name_xpath = f'/html/body/div[1]/div[2]/div[2]/div[2]/div/div[4]/div[4]/div[2]/div[2]/div[2]/table/tbody/tr[{class_index}]/td/div/table/tbody/tr[1]/td[2]/span/a'
                    class_name = self.driver.find_element(By.XPATH, class_name_xpath).text
                    logger.info(f"Processing class: {class_name}")
            
            class_grades = {}
            is_valid_class = True

            row_xpath = f'/html/body/div[1]/div[2]/div[2]/div[2]/div/div[4]/div[4]/div[2]/div[1]/div/div[1]/div[2]/table/tbody/tr[{class_index}]'
                    cells = self.driver.find_elements(By.XPATH, f'{row_xpath}/td')
                    logger.info(f"Found {len(cells)} grade cells for {class_name}")

            for cell_index, cell in enumerate(cells):
                try:
                    text = cell.get_attribute('innerText')
                            if text and text.replace('.', '').isnumeric():
                            if cell_index < len(period_labels):
                                class_grades[period_labels[cell_index]] = float(text)
                            elif text:
                            is_valid_class = False
                            break
                        except Exception as e:
                            logger.error(f"Error processing grade cell {cell_index} for {class_name}: {str(e)}")
                            continue

                    if is_valid_class and class_grades:
                        logger.info(f"Adding grades for {class_name}: {class_grades}")
                        self.grades_raw[class_name] = class_grades
                        filtered_grades = {period: grade for period, grade in class_grades.items() 
                                        if 'C' not in period}
                        if filtered_grades:
                            self.grades[class_name] = filtered_grades

                except Exception as e:
                    logger.error(f"Error processing class {class_index}: {str(e)}")
                    logger.error(traceback.format_exc())
                    continue

            logger.info("Grade extraction completed successfully")
            logger.info(f"Total classes processed: {len(self.grades)}")

        except Exception as e:
            logger.error(f"Error in extract_grades: {str(e)}")
            logger.error(traceback.format_exc())
            raise

    def calculate_gpas(self):
        for period in self.ordered_periods:
        total_gpa = 0
        num_classes = 0
        
            for class_name, class_grades in self.grades.items():
            if period in class_grades:
                grade = class_grades[period]
                gpa = 6.0 - (100 - grade) * 0.1
                total_gpa += gpa
                num_classes += 1
        
        if num_classes > 0:
                self.period_gpas[period] = total_gpa / num_classes

        for period in self.ordered_periods:
        total_gpa = 0
        num_classes = 0
        
            for class_name, class_grades in self.grades.items():
            if period in class_grades:
                grade = class_grades[period]
                
                    if "APA" in class_name:
                    base_gpa = 7.0
                elif "AP" in class_name:
                    base_gpa = 8.0
                else:
                    base_gpa = 6.0
                
                weighted_gpa = base_gpa - (100 - grade) * 0.1
                total_gpa += weighted_gpa
                num_classes += 1
        
        if num_classes > 0:
                self.weighted_period_gpas[period] = total_gpa / num_classes
