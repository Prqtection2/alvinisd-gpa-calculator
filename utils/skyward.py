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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

    def calculate(self):
        try:
            logger.info("Setting up Chrome options...")
            options = webdriver.ChromeOptions()
            
            # Docker-specific Chrome options
            options.add_argument('--headless=new')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--start-maximized')
            options.add_argument('--ignore-certificate-errors')
            options.add_argument('--disable-extensions')
            options.add_argument('--remote-debugging-port=9222')
            options.add_experimental_option('excludeSwitches', ['enable-logging'])
            
            logger.info("Initializing Chrome driver...")
            # Use direct path to Chrome in Docker
            options.binary_location = '/usr/bin/google-chrome'
            service = ChromeService(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            logger.info("Chrome driver initialized successfully")
            
            self.login()
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
            self.driver.get("https://skyward-alvinprod.iscorp.com/scripts/wsisa.dll/WService=wsedualvinisdtx/fwemnu01.w")
            
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
            except:
                # Check for error message
                try:
                    error_element = WebDriverWait(self.driver, 3).until(
                        EC.presence_of_element_located((By.CLASS_NAME, 'validation-error'))
                    )
                    raise Exception("Incorrect username or password. Please check your credentials and try again.")
                except:
                    raise Exception("Login failed. Please double-check your password and try again. If you're sure your password is correct, try again in a few minutes.")

        except Exception as e:
            if "Incorrect username or password" in str(e) or "Login failed" in str(e):
                raise e
            raise Exception("Login failed. Please double-check your password and try again. If you're sure your password is correct, try again in a few minutes.")

    def navigate_to_gradebook(self):
        try:
            logger.info("Attempting to switch to new window...")
            # Wait for new window and switch to it
            WebDriverWait(self.driver, 20).until(lambda d: len(d.window_handles) > 1)
            self.driver.switch_to.window(self.driver.window_handles[1])
            logger.info("Successfully switched to new window")

            # Log the current URL
            logger.info(f"Current URL: {self.driver.current_url}")
            
            # Wait for page to load
            logger.info("Waiting for page to load...")
            time.sleep(5)  # Give the page some time to load
            
            # Log page source for debugging
            logger.info("Page source length: " + str(len(self.driver.page_source)))
            
            logger.info("Looking for gradebook button...")
            # Try different ways to find the gradebook button
            try:
                # First try waiting for element to be clickable
                gradebook_xpath = '/html/body/div[1]/div[2]/div[2]/div[1]/div/ul[2]/li[3]/a'
                logger.info("Waiting for gradebook button to be clickable...")
                gradebook_button = WebDriverWait(self.driver, 20).until(
                    EC.element_to_be_clickable((By.XPATH, gradebook_xpath))
                )
                
                # Try to scroll the button into view
                logger.info("Scrolling to gradebook button...")
                self.driver.execute_script("arguments[0].scrollIntoView(true);", gradebook_button)
                time.sleep(2)  # Wait for scroll to complete
                
                # Try to click using JavaScript
                logger.info("Attempting to click using JavaScript...")
                self.driver.execute_script("arguments[0].click();", gradebook_button)
                
            except Exception as e:
                logger.warning(f"Primary click method failed: {str(e)}")
                # Try alternative methods
                try:
                    logger.info("Trying to find by link text 'Gradebook'...")
                    gradebook_button = WebDriverWait(self.driver, 20).until(
                        EC.element_to_be_clickable((By.LINK_TEXT, "Gradebook"))
                    )
                    ActionChains(self.driver).move_to_element(gradebook_button).click().perform()
                except Exception as e:
                    logger.warning(f"Link text click failed: {str(e)}")
                    logger.info("Trying final fallback with partial link text...")
                    gradebook_button = WebDriverWait(self.driver, 20).until(
                        EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "grade"))
                    )
                    self.driver.execute_script("arguments[0].click();", gradebook_button)

            logger.info("Successfully triggered gradebook button click")

            # Wait for gradebook to load
            logger.info("Waiting for gradebook to load...")
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.XPATH, '/html/body/div[1]/div[2]/div[2]/div[2]/div/div[4]/div[4]/div[2]/div[1]/div/div[1]/div[1]/table/thead/tr/th'))
            )
            logger.info("Gradebook loaded successfully")

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
