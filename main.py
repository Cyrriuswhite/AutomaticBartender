#!/usr/bin/env python

import time
import RPi.GPIO as GPIO
import json
import serial
from neopixel import *
from random import *
import traceback 
import threading
import subprocess
from drinks import drink_list, drink_options
from nextionassociation import nextionAssociation_list

GPIO.setmode(GPIO.BCM)

LED_COUNT=37
LED_PIN=18
LED_FREQ_HZ=800000
LED_DMA=10
LED_INVERT=False
LED_BRIGHTNESS =255
LED_CHANNEL=0

GLASS_DETECTION_PIN = 13

NORMAL_SIZE = 60.0/500.0
TEST_SIZE = 60.0/1500.0

PORT=serial.Serial("/dev/ttyAMA0",baudrate=9600, timeout=1.0)
EOF = "\xff\xff\xff"
GPIO.setup(GLASS_DETECTION_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)


class Command():
    def __init__(self, type, name, attributes = None):
        self.type = type
        self.name = name
        self.attributes = attributes


class Bartender():
    def __init__(self):

        #Initialize GPIO pins with pump configuration from JSon file
        self.pumpConf=Bartender.loadPumpConf()
        for pump in self.pumpConf.keys():
            GPIO.setup(self.pumpConf[pump]["pin"], GPIO.OUT, initial=GPIO.HIGH)


        #SetUp the LED strip
        self.led = Adafruit_NeoPixel(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
        self.led.begin()
        for i in range(0, LED_COUNT):
            self.led.setPixelColor(i,Color(30,30,30))
            self.led.show()

        #SetUp the Nextion display
        PORT.write("page Main"+EOF)
        PORT.write("Security.ON.pco=19785"+EOF)
        PORT.write("Security.OFF.pco=65535"+EOF)
        PORT.write("DrinkConf.sizeNormal.pco=19785"+EOF)
        PORT.write("DrinkConf.sizeTest.pco=65535"+EOF)
        PORT.write("DrinkConf.rapport3p1.pco=19785"+EOF)
        PORT.write("DrinkConf.rapport2p1.pco=65535"+EOF)
        
        #SetUp glass detection 
        self.glassDetectPin = GLASS_DETECTION_PIN
        self.glassDetectIsActivated = True
        #SetUp default glass size
        self.drinkSize = TEST_SIZE

    @staticmethod    
    def loadPumpConf():
        return json.load(open('pump.json'))
    
    @staticmethod
    def editPumpConf(pumpConf):
        with open("pump.json", "w") as jsonFile:
            json.dump(pumpConf, jsonFile)
    
    #def glassDetection(self):
	#	GPIO.add_event_detect(self.glassDetectPin, GPIO.FALLING, callback=self.left_btn, bouncetime=LEFT_PIN_BOUNCE)

    def pour(self, pin, waitTime):
        GPIO.output(pin, GPIO.LOW)
        time.sleep(waitTime)
        GPIO.output(pin, GPIO.HIGH)

    def progressBar(self, waitTime, name):
        PORT.write("page LoadingBar"+EOF)
        PORT.write("name.txt=\"Serving "+name+"\""+EOF)
        interval = waitTime / 100.0
        for x in range(1, 101):
            PORT.write("loadingBar.val="+str(x)+EOF)
            PORT.write("loadingValue.txt=\""+str(x)+"%\""+EOF)
            time.sleep(interval)
        PORT.write("page Main"+EOF)

    def cycleLights(self):
        t = threading.currentThread()
        head  = 0               # Index of first 'on' pixel
        tail  = -10             # Index of last 'off' pixel
        color = 0xFF0000        #  Red

        while getattr(t, "do_run", True):
            self.led.setPixelColor(head, color) # Turn on 'head' pixel
            self.led.setPixelColor(tail, 0)     # Turn off 'tail'
            self.led.show()                     # Refresh strip
            time.sleep(1.0 / 50)             # Pause 20 milliseconds (~50 fps)

            head += 1                        # Advance head position
            if(head >= LED_COUNT):           # Off end of strip?
                head    = 0              # Reset to start
                color >>= 8              # Red->green->blue->black
                if(color == 0): color = 0xFF0000 # If black, reset to red

            tail += 1                        # Advance tail position
            if(tail >= LED_COUNT): tail = 0  # Off end? Reset

    def lightsEndingSequence(self):
        # make lights green
        for i in range(0, LED_COUNT):
            self.led.setPixelColor(i, 0xFF0000)
        self.led.show()

        time.sleep(3)

        # turn lights off
        for i in range(0, LED_COUNT):
            self.led.setPixelColor(i, 0)
        self.led.show() 

    def clean(self):
        
        waitTime = 20
        pumpThreads = []

        # cancel any button presses while the drink is being made
        # self.stopInterrupts()
        self.running = True

        for pump in self.pumpConf.keys():
            pump_t = threading.Thread(target=self.pour, args=(self.pumpConf[pump]["pin"], waitTime))
            pumpThreads.append(pump_t)

        # start the pump threads
        for thread in pumpThreads:
            thread.start()

        # start the progress bar
        self.progressBar(waitTime, "Cleaning")

        # wait for threads to finish
        for thread in pumpThreads:
            thread.join()

        ######## show the main menu
        #self.menuContext.showMenu()

        # sleep for a couple seconds to make sure the interrupts don't get triggered
        time.sleep(2)

    def russianRoulette(self):
        iterator=randint(0,5)
        ing_list=drink_options[iterator]
        ingredients=[{"name":ing_list['name'],"ingredients":{ing_list['value']:50}}]
        for d in ingredients:
            russianRoulette=Command('drink', d["name"], {"ingredients": d["ingredients"]})
        return(russianRoulette)

    def showStats(self):
        cmd = "hostname -I | cut -d\' \' -f1"
        IP = subprocess.check_output(cmd, shell = True )
        cmd = "top -bn1 | grep load | awk '{printf \" %.2f\", $(NF-2)}'"
        CPU = subprocess.check_output(cmd, shell = True )
        cmd = "free -m | awk 'NR==2{printf \"%s/%sMB %.2f%%\", $3,$2,$3*100/$2 }'"
        MemUsage = subprocess.check_output(cmd, shell = True )
        cmd = "df -h | awk '$NF==\"/\"{printf \"%d/%dGB %s\", $3,$2,$5}'"
        Disk = subprocess.check_output(cmd, shell = True )

        print (IP)
        print (CPU)
        print(MemUsage)
        print (Disk)
        PORT.write("ip.txt=\""+IP+"\""+EOF)
        PORT.write("cpu.txt=\""+CPU+"\""+EOF)
        PORT.write("mem.txt=\""+MemUsage+"\""+EOF)
        PORT.write("disk.txt=\""+Disk+"\""+EOF)
        
    def detectSettings(self,command_name):
        if (command_name=="GlassDetectActivate"):
            self.glassDetectIsActivated = True
        elif(command_name=="GlassDetectDeactivate"):
            self.glassDetectIsActivated = False
    
    def sizeSettings(self,command_name):
        
        if (command_name=="NormalSize"):
            self.drinkSize= NORMAL_SIZE
        elif(command_name=="TestSize"):
            self.drinkSize = TEST_SIZE
    

    
   # def drinkSelection(self, Command):
   #     if (Command.type == "drink"):
   #         self.makeDrink(Command.name, Command.attributes["ingredients"])
   #         return True
   #     elif(Command.type == "russianRoulette"):
   #         randomShooter=self.russianRoulette()
   #         self.makeDrink(randomShooter.name,randomShooter.attributes["ingredients"])
   #         return True
   #     elif(Command.type == "pump_selection"):
   #         self.pumpConf[Command.attributes["key"]]["value"] = Command.attributes["value"]
   #         Bartender.writePumpConfiguration(self.pumpConf)
   #         return True
   #     elif(Command.type == "clean"):
   #         self.clean()
   #         return True
   #     elif(Command.type == "showStats"):
   #         self.showStats()
   #         return True
   #     return False

    def makeDrink(self, drink, ingredients):
        if (GPIO.input(self.glassDetectPin) and self.glassDetectIsActivated ==True):
            PORT.write("t0.pco=63488"+EOF)
            print ("No glass detected")
            time.sleep(2);
            PORT.write("t0.pco=0"+EOF)
            return
        # cancel any command made while serving
        self.running = True
        print(ingredients.keys())
        # launch a thread to control lighting
        lightsThread = threading.Thread(target=self.cycleLights)
        lightsThread.start()

        # Parse the drink ingredients and spawn threads for pumps
        maxTime = 0
        pumpThreads = []
        for ing in ingredients.keys():
            for pump in self.pumpConf.keys():
                if ing == self.pumpConf[pump]["value"]:
                    waitTime = ingredients[ing] * self.drinkSize
                    print (waitTime)
                    if (waitTime > maxTime):
                        maxTime = waitTime
                    pump_t = threading.Thread(target=self.pour, args=(self.pumpConf[pump]["pin"], waitTime))
                    pumpThreads.append(pump_t)

        # start the pump threads
        for thread in pumpThreads:
            thread.start()

        # start the progress bar
        self.progressBar(maxTime,drink)

        # wait for threads to finish
        for thread in pumpThreads:
            thread.join()


        # stop the light thread
        lightsThread.do_run = False
        lightsThread.join()

        # show the ending sequence lights
        self.lightsEndingSequence()

        # sleep for a couple seconds to make sure the interrupts don't get triggered
        time.sleep(1);
        # reenable interrupts
        self.running = False
        print("done")
    
    def processCommand(self,nextionCommand):
        nex_page=ord(nextionCommand[1])
        nex_component_id=ord(nextionCommand[2])
        print(nex_page)
        print(nex_component_id)
        command_name=""
        command_type=""
        ###Configure the button press
        for command in nextionAssociation_list:
            if( command["page"]==nex_page and command["component_id"]==nex_component_id):
                command_name =command["name"]
                command_type =command["type"]
        if(command_type=="drink"):
            for d in drink_opts:
                if (d.name==command_name):
                    self.makeDrink(d.name,d.attributes["ingredients"])
                    
        elif(command_type == "shot"):
            bartender.makeDrink(command_name,{command_name:50})       

        elif(command_type == "russianRoulette"):
            randomShooter=self.russianRoulette()
            self.makeDrink(randomShooter.name,randomShooter.attributes["ingredients"])
        elif(command_type=="cleanUp"):
            self.clean()
        elif(command_type == "statShow"):
            self.showStats()
        elif(command_type == "glassDetect"):
           self.detectSettings(command_name)
        elif(command_type == "sizeOfDrink"):
            self.sizeSettings(command_name)
            return
        elif(command_type == "ratio"):
            return
            





    def run(self):
        # main loop
        try:

            try: 

                while True:
                    #letter = raw_input(">")
                    nextionCommand=PORT.readline()
                    if (nextionCommand!=''):
                        self.processCommand(nextionCommand)
                    #time.sleep(0.1)
            except EOFError:
                while True:
                    time.sleep(0.1)
        except KeyboardInterrupt:
            for i in range(0, LED_COUNT):
                self.led.setPixelColor(i,Color(0,0,0))
                self.led.show() 
                
            GPIO.cleanup()       # clean up GPIO on CTRL+C exit  
        GPIO.cleanup()           # clean up GPIO on normal exit 
        traceback.print_exc()



    




drink_opts = []
for d in drink_list:
    drink_opts.append(Command('drink', d["name"], {"ingredients": d["ingredients"]}))

bartender = Bartender()
#bartender.makeDrink("gin",{"gin":50})
bartender.run()
