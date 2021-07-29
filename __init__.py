from modules import cbpi, DBModel, get_db
from modules.core.controller import FermenterController
from modules.core.props import Property
from modules.fermenter import Fermenter
import time
from flask import request
from flask_classy import route
from modules.core.baseview import BaseView


@cbpi.fermentation_controller
class HysteresisWithSlope(FermenterController):

    heater_offset_min = Property.Number("Heater Offset ON", True, 0, description="Offset as decimal number when the heater is switched on. Should be greater then 'Heater Offset OFF'. For example a value of 2 switches on the heater if the current temperature is 2 degrees below the target temperature")
    heater_offset_max = Property.Number("Heater Offset OFF", True, 0, description="Offset as decimal number when the heater is switched off. Should be smaller then 'Heater Offset ON'. For example a value of 1 switches off the heater if the current temperature is 1 degree below the target temperature")
    cooler_offset_min = Property.Number("Cooler Offset ON", True, 0, description="Offset as decimal number when the cooler is switched on. Should be greater then 'Cooler Offset OFF'. For example a value of 2 switches on the cooler if the current temperature is 2 degrees above the target temperature")
    cooler_offset_max = Property.Number("Cooler Offset OFF", True, 0, description="Offset as decimal number when the cooler is switched off. Should be less then 'Cooler Offset ON'. For example a value of 1 switches off the cooler if the current temperature is 1 degree above the target temperature")

    def stop(self):
        super(FermenterController, self).stop()

        self.heater_off()
        self.cooler_off()

    def run(self):
        while self.is_running():
            target_temp = self.get_target_temp()
            self.log('original target temp {}'.format(target_temp))
            try:
                self.update_temp()
            except Exception as err:
                self.log(err)
                
            target_temp = self.get_target_temp()
            self.log('updated target temp {}'.format(target_temp))
            temp = self.get_temp()

            if temp + float(self.heater_offset_min) <= target_temp:
                self.heater_on(100)

            if temp + float(self.heater_offset_max) >= target_temp:
                self.heater_off()

            if temp >= target_temp + float(self.cooler_offset_min):
                self.cooler_on(100)

            if temp <= target_temp + float(self.cooler_offset_max):
                self.cooler_off()
            
            self.sleep(1)

    def update_temp(self):
        active_step = next_step = None

        for idx, s in enumerate(cbpi.cache.get('fermenter')[self.fermenter_id].steps):
            if s.state == 'A':
                active_step = s
            if active_step is not None:
                next_step = s
                break

        if active_step is None or next_step is None:
            return
        start_temp = active_step['temp']
        end_temp = next_step['temp']
        duration = ((active_step['days']*24 + active_step['hours'])*60 + active_step['minutes'])*60
        slope = (end_temp-start_temp)/duration
        running_time = (time.time()-active_step['start'])
        desired_temp = slope*running_time + start_temp
        self.postTargetTemp(self.fermenter_id, desired_temp)


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
