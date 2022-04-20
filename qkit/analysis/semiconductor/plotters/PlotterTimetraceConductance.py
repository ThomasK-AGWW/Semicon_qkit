import matplotlib.pyplot as plt

from qkit.analysis.semiconductor.basic_functionality import PlotterSemiconInit, convert_conductance
from qkit.analysis.semiconductor.basic_functionality import  convert_secs, create_saving_path, make_len_eq


class PlotterTimetraceCond(PlotterSemiconInit):
    """Plots a timetrace of the conductance over time. 
    """
    number_of_traces = 1
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
               
    def plot(self, settings, data_in, nodes, savename="timetrace", label="-", title="Timetrace"):
        """nodes are time and x,y,R of lock-in like ["demod0.timestamp0", "demod0.x0"].
        """
        data = make_len_eq(data_in, nodes)
        self.ax.set_title(title)
        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel("Conductance ($\mu$S)")
        self.ax.plot(convert_secs(data[nodes[0]]), convert_conductance(data[nodes[1]], settings, multiplier=1e6), label)
        plt.savefig(f"{create_saving_path(settings)}/{savename}.png", dpi=self.set_dpi, bbox_inches=self.set_bbox_inches)
        plt.show()
        self.close_delete()