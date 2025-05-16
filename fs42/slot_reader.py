from datetime import datetime
import copy

from fs42 import timings

class SlotReader():

    @staticmethod
    def get_tag(conf, when:datetime):
        response = None
        slot = SlotReader.get_slot(conf, when)
        if slot and "tags" in slot:
            tags = slot['tags']
            
            if type(tags) is list:
                if len(tags) == 1 or when.minute < 30:
                    response = tags[0]
                else:
                    response = tags[1]
            else:
                response = tags

        return response
    
    def get_slot(conf, when:datetime):
        day_str = timings.DAYS[when.weekday()]
        slot_number = str(when.hour)
        response = None
        if day_str in conf:
            if slot_number in conf[day_str]:
                response = conf[day_str][slot_number]
                
        return response
    
    @staticmethod
    def smooth_tags(conf):
        #this function smooths tags through slot boundaries - so if not specified
        last_tag = None
        smoothed = copy.deepcopy(conf)
        for day_index in timings.DAYS:
            for slot_index in timings.OPERATING_HOURS:
                slot_index = str(slot_index)
                if slot_index in conf[day_index]:
                    if 'tags' in conf[day_index][slot_index]:
                        last_tag = conf[day_index][slot_index]
                    elif 'continued' in conf[day_index][slot_index]:
                        if conf[day_index][slot_index]['continued'] == True:
                            smoothed[day_index][slot_index]['tags'] = last_tag['tags']
        return smoothed
