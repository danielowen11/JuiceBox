#!/usr/bin/python2.7
##@package juicebox
#
#A device to intake user credentials, authenticate against granted rights, and enable/disable usage based on those.

from __future__ import print_function

import httplib
import json
import logging
import signal
import sys
import time

import RPi.GPIO as GPIO
import requests

import MFRC522

# Debug logging, do not modify
httplib.HTTPConnection.debuglevel = 1
logging.basicConfig(format='%(asctime)s %(message)s')
logging.getLogger().setLevel(logging.DEBUG)
req_log = logging.getLogger('requests.packages.urllib3')
req_log.setLevel(logging.DEBUG)
req_log.propagate = True

pin_button = 40
pin_green = 7
pin_red = 8
pin_connect = 3
pin_led_ring = 33

device_id = "DEV_ID"
GPIO.setmode(GPIO.BOARD)
GPIO.setup(pin_button, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.add_event_detect(pin_button, GPIO.FALLING)
GPIO.setup(pin_connect, GPIO.OUT)
serverURL = "FLUD_BASE/juicebox.php"
GPIO.output(pin_connect, False)
GPIO.setup(pin_led_ring, GPIO.OUT)
GPIO.output(pin_led_ring, False)

headers = {'authorization': "FLUD_KEY"}

## The central object of the program. It contains data for the current session, and functions for communicating with the external database.
#
# Data stored within the Juicebox object includes:
# - the RFID numbers for the operator and employee overseeing use of the device
# - the user details for both indidivuals (including the employee's authorization level)
class Juicebox:

    ## The constructor.
    def __init__(self):    
        ## the RFID number for the operator.
        self.rid_1 = ""
        ## the RFID number for the employee.
        self.rid_2 = ""
        ### the JSON object for the operator.
        #self.operator = None
        ### the JSON object for the employee.
        #self.employee = None
        ## a variable for advancing the code flow to the second part of the for loop.
        self.phase2 = False

    ## Grabs the RFID number from the user's card, then retrieves the details from the database corresponding to the given RFID.
    # @param rid A variable which stores the RFID number for the user details being requested.
    def get_details(self):
        # communication with the RFID reader to retrieve the RFID number
        (status, TagType) = MIFAREReader.MFRC522_Request(MIFAREReader.PICC_REQIDL)
        (status, uid) = MIFAREReader.MFRC522_Anticoll()
        if status == MIFAREReader.MI_OK:
            # place the RFID in the parameter variable
            rid = str(uid[0]) + str(uid[1]) + str(uid[2]) + str(uid[3])
            # check if the user being read is a student or employee by using the "phase2" variable
            # to know where it is in the while statement 
            user = "Staff" if self.phase2 else "Operator"
            print(user, "RFID:", rid, file=sys.stderr)
            
            try:
                payload = {"type": "check_status_rfid", "number": rid}
                r = requests.request("POST", serverURL, json=payload, headers=headers)
                response = r.json()

                r.raise_for_status()
                print(response, file=sys.stderr)

                ## The JSON object which holds the user details.
                json_obj = json.loads(json.dumps(response))
                print(user, "Level:", json_obj["role"], file=sys.stderr)
            except ConnectionError as e:
                response = e + ": Unable to connect. Verify connection."
                print(response, file=sys.stderr)
                self.blink_twice()
                return False, 0
            except HTTPError as e:
                response = e + ": Request to HTTP server returned unsuccessful status code."
                print(response, file=sys.stderr)
                self.blink_twice()
                return False, 0
            except ValueError as e:
                response = e + ": JSON parse failure."
                print(response, file=sys.stderr)
                self.blink_twice()
                return False, 0
            except Exception as e:
                response = e + ": This exception in Juicebox.get_details() lacks error handling. Codebase is incomplete."
                print(response, file=sys.stderr)
                self.blink_twice()
                return False, 0
            else:
                self.blink()
                return True, rid

        return False, 0

    ## Checks if the transaction is authorized, given the two users (operator and employee) trying to use the device.
    # @param id_number the RFID number for the operator.
    # @param id_number_2 the RFID number for the employee.
    def check_if_authorized(self, id_number, id_number_2):
        try:
            payload = {"type": "rfid_double", "number": id_number, "number_employee": id_number_2, "device": device_id}
            r = requests.request("POST", serverURL, json=payload, headers=headers)
            response = r.json()
        except ConnectionError as e:
            response = e + ": Improper pair of RFID values entered, or Unable to connect."
            print(response, file=sys.stderr)
            self.blink_twice()
            return response
        except HTTPError as e:
            response = e + ": Request to HTTP server returned unsuccessful status code during RFID authorization phase."
            print(response, file=sys.stderr)
            self.blink_twice()
            return False, 0
        except Exception as e:
            response = e + ": This exception in Juicebox.check_if_authorized() lacks error handling. Codebase is incomplete."
            print(response, file=sys.stderr)
            self.blink_twice()
            return response
        else:
            return response

    ## Runs if the transaction is successful. Logs the instance of the device's use to the external database.
    def finish(self):
        GPIO.output(pin_connect, True)
        GPIO.output(pin_led_ring, True)
        time.sleep(0.5)
        GPIO.wait_for_edge(pin_button, GPIO.FALLING)
        payload = {"type": "end_transaction", "dev_id": device_id}
        try:
            r = requests.request("POST", serverURL, json=payload, headers=headers)
            response = r.json()
        except ConnectionError as e:
            response = e + "Input to end transaction is somehow invalid, or Unable to connect."
            print(response, file=sys.stderr)
            self.blink_twice()
            return response
        except HTTPError as e:
            response = e + ": Request to HTTP server returned unsuccessful status code during transaction completion phase."
            print(response, file=sys.stderr)
            self.blink_twice()
            return False, 0
        except Exception as e:
            response = e + ": This exception in Juicebox.finish() lacks error handling. Codebase is incomplete."
            print(response, file=sys.stderr)
            self.blink_twice()
            return response
        else:
            print("End Transaction:", response, file=sys.stderr)

        GPIO.output(pin_connect, False)
        GPIO.output(pin_led_ring, False)
        return response

    ## Creates a flash on the button LED, which signals successful entry.
    def blink(self):
        time.sleep(0.5)
        GPIO.output(pin_led_ring, True)
        time.sleep(0.25)
        GPIO.output(pin_led_ring, False)
        time.sleep(0.5)

    ## Creates two flashes on the button LED, which signals an incorrect prompt.
    def blink_twice(self):
        global pin_led_ring
        time.sleep(0.5)
        GPIO.output(pin_led_ring, True)
        time.sleep(0.25)
        GPIO.output(pin_led_ring, False)
        time.sleep(0.25)
        GPIO.output(pin_led_ring, True)
        time.sleep(0.25)
        GPIO.output(pin_led_ring, False)

    ## Resets all code-flow related variables.
    def refresh(self):
        self.phase2 = False

# end of Juicebox Class


# this is from the MFC library, it is to ensure safe exit
continue_reading = True
def end_read(signal, frame):
    print("Ctrl+C captured, ending read.", file=sys.stderr)
    continue_reading = False
    quit()
    GPIO.cleanup()

signal.signal(signal.SIGINT, end_read)
MIFAREReader = MFRC522.MFRC522()



def main():

    juicebox = Juicebox()

    while continue_reading:
        if (GPIO.event_detected(pin_button) and juicebox.phase2 == False): # if the button is pressed
            valid_id, juicebox.rid_1 = juicebox.get_details() # get operator details
            if (valid_id):
                juicebox.phase2 = True # continue on to read for employee details

        if (juicebox.phase2):
            valid_id, juicebox.rid_2 = juicebox.get_details() # get employee details
            if (valid_id):
                transaction = juicebox.check_if_authorized(juicebox.rid_1, juicebox.rid_2) # check if the employee ID is the authorized level
                print("Status:", transaction, file=sys.stderr)
                try:
                    if transaction[u'authorized'] == "Y": # if the employee is the authorized level
                        juicebox.finish()
                        juicebox.refresh()
                        continue
                    else:
                        juicebox.blink_twice()
                        juicebox.refresh()
                        continue
                except Exception:
                    print("Error parsing json of the authorization ... check to make sure the server is returning json.", file=sys.stderr)
                    juicebox.refresh()
                    continue

        time.sleep(0.1)

if __name__ == '__main__':
    main()
