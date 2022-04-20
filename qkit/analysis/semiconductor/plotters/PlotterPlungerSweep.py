import numpy as np
import copy
import matplotlib.pyplot as plt
from scipy import signal
from scipy.optimize import curve_fit

from qkit.analysis.semiconductor.basic_functionality import PlotterSemiconInit, convert_conductance, map_array_to_index
from qkit.analysis.semiconductor.basic_functionality import  convert_secs, create_saving_path, make_len_eq

class PlotterPlungerSweep(PlotterSemiconInit):
    """Plots plunger gate sweeps and (if given) overlays tangent.
    """
    number_of_traces = 1

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def plot(self, settings, settings_plunger, data_in, nodes, fit_params=None, savename="plunger_sweep", color="r", x_limits=[]):
        data = make_len_eq(data_in, nodes)
        y_axis_factor = 1000  #scales y axis to mV
        self.ax.set_title("Plunger Gate Sweep")
        self.ax.set_xlabel("Voltage (V)")
        self.ax.set_ylabel("Lock-in Voltage (mV)")
        self.data_x = data[nodes[0]]
        self.data_y = data[nodes[1]]*y_axis_factor
        if len(x_limits) == 2:
            self.ax.set_xlim(x_limits)
        self.ax.plot(self.data_x, self.data_y)
        if fit_params != None:
            poly1d_fn = np.poly1d(fit_params["fit_coef"])
            self.data_x_fit = self.data_x[fit_params["index_begin"] : fit_params["index_end"]]
            self.ax.plot(self.data_x_fit, poly1d_fn(self.data_x_fit)*y_axis_factor, color, 
            label=f"slope: {fit_params['fit_coef'][0]*y_axis_factor:.0f} mV/V")
            self.ax.legend()
        plt.savefig(f"{create_saving_path(settings_plunger)}/{savename}.png", dpi=self.set_dpi, bbox_inches=self.set_bbox_inches)
        plt.savefig(f"{create_saving_path(settings)}/{savename}.png", dpi=self.set_dpi, bbox_inches=self.set_bbox_inches) 
        plt.show() 
        self.close_delete()