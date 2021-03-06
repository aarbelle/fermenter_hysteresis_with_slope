from modules import cbpi, DBModel, get_db
from modules.core.controller import FermenterController
from modules.core.props import Property
from modules.fermenter import Fermenter
import time
from flask import request
from flask_classy import route
from modules.core.baseview import BaseView
from time import strftime, localtime

@cbpi.fermentation_controller
class HysteresisWithSlope(FermenterController):

    heater_offset_min = Property.Number("Heater Offset ON", True, 0, description="Offset as decimal number when the heater is switched on. Should be greater then 'Heater Offset OFF'. For example a value of 2 switches on the heater if the current temperature is 2 degrees below the target temperature")
    heater_offset_max = Property.Number("Heater Offset OFF", True, 0, description="Offset as decimal number when the heater is switched off. Should be smaller then 'Heater Offset ON'. For example a value of 1 switches off the heater if the current temperature is 1 degree below the target temperature")
    cooler_offset_min = Property.Number("Cooler Offset ON", True, 0, description="Offset as decimal number when the cooler is switched on. Should be greater then 'Cooler Offset OFF'. For example a value of 2 switches on the cooler if the current temperature is 2 degrees above the target temperature")
    cooler_offset_max = Property.Number("Cooler Offset OFF", True, 0, description="Offset as decimal number when the cooler is switched off. Should be less then 'Cooler Offset ON'. For example a value of 1 switches off the cooler if the current temperature is 1 degree above the target temperature")
    cooler_delay_min = Property.Number("Cooler Delay (Min)", True, 3, description="Delay (in minutes) to turn on cooler after last turn off")
    cooler_delay = None
    last_cooler_off = None
    reached_temp = False
    direction = None
    def stop(self):
        super(FermenterController, self).stop()

        self.heater_off()
        self.cooler_off()
	self.last_cooler_off = time.time()

    @cbpi.try_catch('Fermenter')
    def run(self):
        if self.cooler_delay is None:
		self.cooler_delay = float(self.cooler_delay_min)*60
    		self.last_cooler_off = 0.	
	#self.log('running')
        while self.is_running():
	    if self.reached_temp:
		heater_offset_min = self.heater_offset_min
		heater_offset_max = self.heater_offset_max
		cooler_offset_max = self.cooler_offset_max
		cooler_offset_min = self.cooler_offset_min
	    else:
		heater_offset_min = 0
		heater_offset_max = 0
		cooler_offset_max = 0
		cooler_offset_min = 0
		
            target_temp = self.get_target_temp()
            #self.log('original target temp {}'.format(target_temp))
            try:
                self.update_temp()
            except Exception as err:
            #    self.log(err)
		pass
                
            target_temp = self.get_target_temp()
            #self.log('updated target temp {}'.format(target_temp))
            temp = self.get_temp()
	    if not self.reached_temp and self.direction is None:
		if temp < target_temp:
	            self.direction = 'up'
		elif temp > target_temp:
	            self.direction = 'down'
		else:
		    self.reached_temp = True
	    elif not self.reached_temp:
		if (self.direction == 'up' and temp >= target_temp) or (self.direction == 'down' and temp <= target_temp):
			self.reached_temp = True
	
            #self.log('current temp {}'.format(temp))
	    if temp is None:
		continue
            if temp + float(heater_offset_min) <= target_temp:
                self.heater_on(100)

            if temp + float(heater_offset_max) >= target_temp and self.reached_temp:
                self.heater_off()
            #self.log('current time: {}, last off + delay {}'.format(time.time(), (self.last_cooler_off + self.cooler_delay)))
            if temp >= target_temp + float(cooler_offset_min) and time.time() > (self.last_cooler_off + self.cooler_delay):
                self.cooler_on(100)

            if temp <= target_temp + float(cooler_offset_max) and self.reached_temp:
                self.cooler_off()
		self.last_cooler_off = time.time()
            
            self.sleep(1)

    def update_temp(self):
        active_step = next_step = None
	
        for idx, s in enumerate(cbpi.cache.get('fermenter')[self.fermenter_id].steps):
            if active_step is not None:
                next_step = s
		#self.log('Found Next Step {}'.format(s))
                break
            if s.state == 'A':
                active_step = s
		#self.log('Found Active Step {}'.format(s))


        if active_step is None or next_step is None:
            return
        start_temp = active_step.temp
        end_temp = next_step.temp
	#self.log('Start Temp {}. End Temp {}'.format(start_temp, end_temp))
	#self.log('Days: {}, Hours{}, Min{}'.format(active_step.days,active_step.hours,active_step.minutes))
        duration = float(((active_step.days*24 + active_step.hours)*60 + active_step.minutes)*60)
	#self.log('Duration {}'.format(duration))
        slope = float(end_temp-start_temp)/duration
	#self.log('Slope {}'.format(slope))
	#self.log('Time {}, timer start {} duration {} '.format(time.time(), active_step.timer_start, duration))
        running_time = (time.time()-active_step.timer_start + duration)
	#self.log('Running Time {}'.format(running_time))
        desired_temp = round((slope*running_time + start_temp)*100)/100
	#self.log('Desired Temp {}'.format(desired_temp))
	if desired_temp == self.get_target_temp():
		return
	with cbpi.app.app_context():
	        self.postTargetTemp(self.fermenter_id, desired_temp)
	#self.log('Updated Desired Temp {}'.format(desired_temp))


    @route('/<int:id>/targettemp/<temp>', methods=['POST'])
    def postTargetTemp(self, id, temp):
        if temp is None or not temp:
            return ('', 500)
        id = int(id)
        temp = float(temp)
        cbpi.cache.get('fermenter')[id].target_temp = float(temp)
        Fermenter.update(**cbpi.cache.get('fermenter')[id].__dict__)
        cbpi.emit("UPDATE_FERMENTER_TARGET_TEMP", {"id": id, "target_temp": temp})
        return ('', 204)
    
    def log(self, text):
	filename = "./logs/fermenter_slope.log"
	formatted_time = strftime("%Y-%m-%d %H:%M:%S", localtime())
	with open(filename, "a") as file:
		file.write("%s,%s\n" % (formatted_time, text))
