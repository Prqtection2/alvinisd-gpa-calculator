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
        # Take screenshot and convert to base64
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
        # Define the correct order of periods
        self.period_order = ['1U1', '1U2', 'NW1', '2U1', '2U2', 'NW2', 'EX1', 'SM1', 
                            '3U1', '3U2', 'NW3', '4U1', '4U2', 'NW4', 'EX2', 'SM2', 'YR']
        self.ordered_periods = []
        
        # Only start Xvfb on Linux (Render)
        if platform.system() == 'Linux' and not os.environ.get('DISPLAY'):
            subprocess.Popen(['Xvfb', ':99', '-screen', '0', '1024x768x24'])
            os.environ['DISPLAY'] = ':99'

    def calculate(self):
        try:
            logger.info("Setting up Chrome options...")
            options = webdriver.ChromeOptions()
            
            # Set up options based on environment
            if platform.system() == 'Linux':  # Render
                chrome_binary = os.environ.get('CHROME_BIN', '/usr/bin/google-chrome')
                logger.info(f"Using Chrome binary: {chrome_binary}")
                options.binary_location = chrome_binary
                
                # Required arguments for running on Render
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-dev-shm-usage')
                options.add_argument('--disable-gpu')
                options.add_argument('--disable-software-rasterizer')
                options.add_argument('--disable-features=VizDisplayCompositor')
                options.add_argument('--disable-extensions')
                options.add_argument('--single-process')
                options.add_argument('--remote-debugging-port=9222')
                options.add_argument('--window-size=1920,1080')
                options.add_argument('--start-maximized')
                options.add_argument('--disable-setuid-sandbox')
                options.add_argument('--disable-web-security')
                options.add_argument('--headless=new')  # Use new headless mode
            else:  # Local
                options.add_argument('--headless=new')
            
            # Common options
            options.add_argument('--ignore-certificate-errors')
            options.add_experimental_option('excludeSwitches', ['enable-logging'])
            
            logger.info("Initializing Chrome driver...")
            try:
                if platform.system() == 'Windows':
                    service = ChromeService(ChromeDriverManager().install())
                else:
                    # For Linux/Render, try to use system Chrome
                    self.driver = webdriver.Chrome(options=options)
                    logger.info("Chrome driver initialized using system Chrome")
                    return
            except Exception as e:
                logger.error(f"Error initializing Chrome driver: {str(e)}")
                # Fallback to direct initialization
                logger.info("Attempting fallback Chrome initialization...")
                self.driver = webdriver.Chrome(options=options)
                logger.info("Fallback Chrome initialization successful")

            self.login()
            
            # Take screenshot after login
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
            # Take screenshot on error
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
            
            # Check if we're on the correct page
            current_url = self.driver.current_url
            logger.info(f"Current URL before login: {current_url}")
            if "fwemnu01.w" not in current_url:
                logger.error(f"Unexpected URL before login: {current_url}")
                self.driver.get(login_url)  # Try to load the login page again
                time.sleep(2)  # Wait for page to load
            
            logger.info("Waiting for username input...")
            username_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, '/html/body/form[1]/div/div/div[4]/div[2]/div[1]/div[2]/div/table/tbody/tr[1]/td[2]/input'))
            )
            username_input.send_keys(self.username)
            logger.info("Username entered successfully")

            # Enter password
            password_input = self.driver.find_element(By.XPATH, '/html/body/form[1]/div/div/div[4]/div[2]/div[1]/div[2]/div/table/tbody/tr[2]/td[2]/input')
            password_input.send_keys(self.password)

            # Click sign-in button
            sign_in_button = self.driver.find_element(By.XPATH, '/html/body/form[1]/div/div/div[4]/div[2]/div[1]/div[2]/div/table/tbody/tr[7]/td/a')
            sign_in_button.click()

            # Wait for new window to appear or error message
            try:
                WebDriverWait(self.driver, 10).until(lambda d: len(d.window_handles) > 1)
                logger.info("New window detected after login")
            except:
                # Check for error message
                try:
                    error_element = WebDriverWait(self.driver, 3).until(
                        EC.presence_of_element_located((By.CLASS_NAME, 'validation-error'))
                    )
                    raise Exception("Incorrect username or password. Please check your credentials and try again.")
                except:
                    # Check if we're redirected to home page
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
            
            # Take screenshot before navigation
            save_screenshot_base64(self.driver, "before_navigation")
            
            if len(self.driver.window_handles) > 1:
                logger.info("Multiple windows detected, switching to new window...")
                self.driver.switch_to.window(self.driver.window_handles[1])
                logger.info("Successfully switched to new window")
                # Take screenshot after window switch
                save_screenshot_base64(self.driver, "after_window_switch")
            else:
                logger.info("Single window detected, continuing in current window")
            
            # Wait for page to load
            logger.info("Waiting for page to load...")
            time.sleep(5)
            
            # Log page source and check for content
            page_source = self.driver.page_source
            logger.info("Page source length: " + str(len(page_source)))
            
            # Log all links on the page
            links = self.driver.find_elements(By.TAG_NAME, "a")
            logger.info("Found links on page:")
            for link in links:
                try:
                    href = link.get_attribute("href")
                    text = link.text
                    logger.info(f"Link text: '{text}', href: '{href}'")
                except:
                    continue
            
            # Try to find any navigation elements to verify page loaded
            logger.info("Verifying page loaded correctly...")
            try:
                nav_elements = self.driver.find_elements(By.TAG_NAME, "a")
                logger.info(f"Found {len(nav_elements)} navigation elements")
                if len(nav_elements) == 0:
                    raise Exception("No navigation elements found")
            except Exception as e:
                logger.error(f"Error finding navigation elements: {str(e)}")
                logger.info("Attempting page refresh...")
                self.driver.refresh()
                time.sleep(5)
            
            logger.info("Looking for gradebook button...")
            gradebook_found = False
            max_attempts = 3
            
            for attempt in range(max_attempts):
                try:
                    logger.info(f"Attempt {attempt + 1} to find gradebook button")
                    
                    # Try different locator strategies
                    locator_strategies = [
                        (By.XPATH, '/html/body/div[1]/div[2]/div[2]/div[1]/div/ul[2]/li[3]/a'),
                        (By.LINK_TEXT, "Gradebook"),
                        (By.PARTIAL_LINK_TEXT, "grade"),
                        (By.CSS_SELECTOR, "a[href*='grade']")
                    ]
                    
                    for locator in locator_strategies:
                        try:
                            logger.info(f"Trying to find gradebook using {locator[0]}")
                            gradebook_button = WebDriverWait(self.driver, 30).until(
                                EC.element_to_be_clickable(locator)
                            )
                            
                            # Try to scroll the button into view
                            logger.info("Scrolling to gradebook button...")
                            self.driver.execute_script("arguments[0].scrollIntoView(true);", gradebook_button)
                            time.sleep(2)
                            
                            # Try multiple click methods
                            click_methods = [
                                lambda: gradebook_button.click(),
                                lambda: self.driver.execute_script("arguments[0].click();", gradebook_button),
                                lambda: ActionChains(self.driver).move_to_element(gradebook_button).click().perform()
                            ]
                            
                            for click_method in click_methods:
                                try:
                                    click_method()
                                    gradebook_found = True
                                    break
                                except Exception as click_error:
                                    logger.warning(f"Click method failed: {str(click_error)}")
                                    continue
                            
                            if gradebook_found:
                                break
                                
                        except Exception as locator_error:
                            logger.warning(f"Locator strategy failed: {str(locator_error)}")
                            continue
                    
                    if gradebook_found:
                        break
                        
                except Exception as attempt_error:
                    logger.warning(f"Attempt {attempt + 1} failed: {str(attempt_error)}")
                    if attempt < max_attempts - 1:
                        logger.info("Refreshing page and trying again...")
                        self.driver.refresh()
                        time.sleep(5)
                    continue
            
            if not gradebook_found:
                raise Exception("Failed to find or click gradebook button after all attempts")
            
            logger.info("Successfully triggered gradebook button click")
            
            # Wait for gradebook to load with increased timeout
            logger.info("Waiting for gradebook to load...")
            try:
                WebDriverWait(self.driver, 45).until(
                    EC.presence_of_element_located((By.XPATH, '/html/body/div[1]/div[2]/div[2]/div[2]/div/div[4]/div[4]/div[2]/div[1]/div/div[1]/div[1]/table/thead/tr/th'))
                )
                logger.info("Gradebook loaded successfully")
            except Exception as timeout_error:
                logger.error("Timeout waiting for gradebook to load")
                # Take a screenshot before raising the error
                self.driver.save_screenshot("gradebook_timeout.png")
                raise

        except Exception as e:
            logger.error(f"Error in navigate_to_gradebook: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            # Take a screenshot for debugging
            try:
                screenshot_path = "error_screenshot.png"
                self.driver.save_screenshot(screenshot_path)
                logger.info(f"Screenshot saved to {screenshot_path}")
            except Exception as screenshot_error:
                logger.error(f"Failed to take screenshot: {str(screenshot_error)}")
            raise

    def extract_grades(self):
        try:
            logger.info("Starting grade extraction...")
            # Extract grading periods
            logger.info("Finding grading periods...")
            grading_periods_xpath = '/html/body/div[1]/div[2]/div[2]/div[2]/div/div[4]/div[4]/div[2]/div[1]/div/div[1]/div[1]/table/thead/tr/th'
            grading_periods = self.driver.find_elements(By.XPATH, grading_periods_xpath)
            logger.info(f"Found {len(grading_periods)} grading periods")
            
            # Store period labels
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

            # Filter periods and maintain the correct order
            self.ordered_periods = [period for period in self.period_order 
                                  if period in period_labels and 'C' not in period]
            logger.info(f"Ordered periods: {self.ordered_periods}")

            # Get classes container
            logger.info("Finding classes container...")
            classes_container_xpath = '/html/body/div[1]/div[2]/div[2]/div[2]/div/div[4]/div[4]/div[2]/div[2]/div[2]/table/tbody'
            classes_container = self.driver.find_element(By.XPATH, classes_container_xpath)
            class_rows = classes_container.find_elements(By.XPATH, './tr')
            logger.info(f"Found {len(class_rows)} class rows")

            # Extract grades for each class
            for class_index, class_row in enumerate(class_rows, 1):
                try:
                    logger.info(f"Processing class {class_index}/{len(class_rows)}")
                    # Get class name
                    class_name_xpath = f'/html/body/div[1]/div[2]/div[2]/div[2]/div/div[4]/div[4]/div[2]/div[2]/div[2]/table/tbody/tr[{class_index}]/td/div/table/tbody/tr[1]/td[2]/span/a'
                    class_name = self.driver.find_element(By.XPATH, class_name_xpath).text
                    logger.info(f"Processing class: {class_name}")
                    
                    # Get grades
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
                            elif text:  # If non-numeric grade found
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
        # Calculate unweighted GPAs
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

        # Calculate weighted GPAs
        for period in self.ordered_periods:
            total_gpa = 0
            num_classes = 0
            
            for class_name, class_grades in self.grades.items():
                if period in class_grades:
                    grade = class_grades[period]
                    
                    # Determine base GPA
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
