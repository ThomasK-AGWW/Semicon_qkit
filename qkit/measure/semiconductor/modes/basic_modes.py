import numpy as np
import collections

from qkit.measure.semiconductor.modes.mode_base import ModeBase

def makehash():
    return collections.defaultdict(makehash)

class PulseParameter(ModeBase):
    def __init__(self, fh, measurement_settings) -> None:
        self.fh = fh
        self.measurement_settings = measurement_settings
        self.unit = "a.u."
        self.tag = self.create_tag()
        self.total_sum = makehash()
        self.divider = makehash()

    def create_coordinates(self):
        for name, measurement in self.measurement_settings.items():
            self.fh.update_coordinates(self.tag, measurement["loop_range_pp"], 
                                        f"{self.tag}:{measurement['loop_step_name_pp']}.{name}",
                                        name)
    
    def create_datasets(self, additional_coords):
        for name, measurement in self.measurement_settings.items():
            self.divider[name] = 0 
            for node in measurement["data_nodes"]:
                coords = [self.fh.multiplexer_coords[self.tag][name]] + additional_coords
                self.fh.add_dset(f"{self.tag}:{name}.{node}", coords, self.unit)
                self.total_sum[name][node] = 0

    def fill_file(self, latest_data, data_location):
        for measurement_name, node_values in latest_data.items():
            #If latest data is empty for one measurement, skip it
            first_node = list(node_values.keys())[0]
            collected_averages = len(node_values[first_node])
            if collected_averages== 0: continue
            self.divider[measurement_name] += collected_averages
            for node_name, node_value in node_values.items():
                self.total_sum[measurement_name][node_name] += np.sum(np.average(node_value, axis = 2), axis = 0)
                value = self.total_sum[measurement_name][node_name]/self.divider[measurement_name]
                self.fh.write_to_file(f"{self.tag}:{measurement_name}.{node_name}", value, data_location)    
    
    def reset(self):
        self.total_sum = makehash()
        self.divider = makehash()

#TODO: Add NoAvg
class NoAvg(ModeBase):
    def __init__(self, fh, measurement_settings) -> None:
        self.fh = fh
        self.measurement_settings = measurement_settings
        self.unit = "a.u."
        self.tag = self.create_tag()
        self.column = makehash()

    def create_coordinates(self):
        for name, measurement in self.measurement_settings.items():
            self.fh.update_coordinates(f"{self.tag}.iter", np.arange(measurement["averages"] * measurement["measurement_count"]), 
                                        f"{self.tag}:iterations.{name}",
                                        name)
            self.fh.update_coordinates(f"{self.tag}.tt", measurement["loop_range_tt"], 
                                        f"{self.tag}:{measurement['loop_step_name_tt']}.{name}",
                                        name)
    
    def create_datasets(self, additional_coords):
        for name, measurement in self.measurement_settings.items():
            for node in measurement["data_nodes"]:
                coords = [self.fh.multiplexer_coords[f"{self.tag}.tt"][name], self.fh.multiplexer_coords[f"{self.tag}.iter"][name]] + additional_coords
                self.fh.add_dset(f"{self.tag}:{name}.{node}", coords, self.unit)
                self.column[name][node] = 0

    def fill_file(self, latest_data, data_location):
        for measurement_name, node_values in latest_data.items():
            #If latest data is empty for one measurement, skip it
            first_node = list(node_values.keys())[0]
            collected_averages = len(node_values[first_node])
            if collected_averages== 0: continue
            for node_name, node_value in node_values.items():
                for grid in node_value:
                    for single_trace in grid:
                        self.fh.write_to_file(f"{self.tag}:{measurement_name}.{node_name}", single_trace, 
                        (self.column[measurement_name][node_name],) + data_location)
                        self.column[measurement_name][node_name] += 1
    
    def reset(self):
        print("Resetting NoAvg!")        
        print(list(self.column.keys())[0])
        self.column = makehash()
#TODO: Add PpvsT
#TODO: Add TimeTrace