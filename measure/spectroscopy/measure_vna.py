# JB@KIT 04/2015
# VNA measurement class supporting function dependent measurement


import numpy as np
import logging
import matplotlib.pylab as plt
from scipy.optimize import curve_fit
import time
from time import sleep
import qt

from qkitgui.notebook.Progress_Bar import Progress_Bar


#ttip = qt.instruments.get('ttip')
#vna = qt.instruments.get('vna')
#mw_src1 = qt.instruments.get('mw_src1')
vcoil = qt.instruments.get('vcoil')

##########################################################################################################################

class spectrum(object):
	
	'''
	useage:
	
	m = spectrum()
	m2 = spectrum(vna_select = 'vna2', mw_src_select = 'mw_src1')   #where 'vna2'/'mw_src1' is the qt.instruments name
	
	m.set_x_parameters(arange(-0.05,0.05,0.01),'flux coil current (mA)',coil.set_current)
	m.set_y_parameters(arange(4e9,7e9,10e6),'excitation frequency (Hz)',mw_src1.set_frequency)
	
	m.gen_fit_function(...)   several times
	
	m.measure_XX()
	'''
	
	def __init__(self, vna_select = 'vna', mw_src_select = 'mw_src1'):
	
		global vna
		vna = qt.instruments.get(vna_select)
		global mw_src1
		mw_src1 = mw_src1 = qt.instruments.get(mw_src_select)
		
		self.landscape = None
		self.span = 200e6   #specified in Hz
		self.tdx = 0.002
		self.tdy = 0.002
		#self.op='amppha'
		#self.ref=False
		#self.ref_meas_func=None
		self.comment = None
		self.plot3D = True
		self.plotlive = True
		
		self.x_set_obj = None
		self.y_set_obj = None
		
	def set_span(self, span):
		self.span = span
		
	def get_span(self):
		return self.span

	def set_x_parameters(self, x_vec, x_coordname, x_set_obj):
		self.x_vec = x_vec
		self.x_coordname = x_coordname
		self.x_set_obj = x_set_obj
		self.delete_fit_function()
		
	def set_y_parameters(self, y_vec, y_coordname, y_set_obj):
		self.y_vec = y_vec
		self.y_coordname = y_coordname
		self.y_set_obj = y_set_obj
		self.delete_fit_function()
		
	def set_tdx(self, tdx):
		self.tdx = tdx
		
	def set_tdy(self, tdy):
		self.tdy = tdy
		
	def get_tdx(self):
		return self.tdx
		
	def get_tdy(self):
		return self.tdy

	def f_parab(self,x,a,b,c):
		return a*(x-b)**2+c
	def f_hyp(self,x,a,b,c):
		return a*np.sqrt((x/b)**2+c)
		
	def gen_fit_function(self, curve_f, curve_p, units = '', p0 = [-1,0.1,7]):
	
		'''
		curve_f: 'parab', 'hyp', specifies the fit function to be employed
		curve_p: set of points that are the basis for the fit in the format [[x1,x2,x3,...],[y1,y2,y3,...]], frequencies in Hz
		units: set this to 'Hz' in order to avoid large values that cause the fit routine to diverge
		p0 (optional): start parameters for the fit, must be an 1D array of length 3 ([a,b,c])
		
		adds a trace to landscape
		'''
		
		if self.landscape == None:
			self.landscape = []
		
		x_fit = curve_p[0]
		if units == 'Hz':
			y_fit = np.array(curve_p[1])*1e-9
		else:
			y_fit = np.array(curve_p[1])
		
		try:
			if curve_f == 'parab':
				popt, pcov = curve_fit(self.f_parab, x_fit, y_fit, p0=p0)
				if units == 'Hz':
					self.landscape.append(1e9*self.f_parab(self.x_vec, *popt))
				else:
					self.landscape.append(self.f_parab(self.x_vec, *popt))
			elif curve_f == 'hyp':
				popt, pcov = curve_fit(self.f_hyp, x_fit, y_fit, p0=p0)
				if units == 'Hz':
					self.landscape.append(1e9*self.f_hyp(self.x_vec, *popt))
				else:
					self.landscape.append(self.f_hyp(self.x_vec, *popt))
			else:
				print 'function type not known...aborting'
				raise ValueError
		except Exception as message:
			print 'fit not successful:', message
			popt = p0

	def delete_fit_function(self, n = None):
		if n == None:
			self.landscape = None
		else:
			self.landscape = np.delete(self.landscape,n,axis=0)
			
	def plot_fit_function(self, num_points = 100):
		'''
		try:
			x_coords = np.linspace(self.x_vec[0], self.x_vec[-1], num_points)
		except Exception as message:
			print 'no x axis information specified', message
			return
		'''
		if self.landscape != None:
			for trace in self.landscape:
				try:
					#plt.clear()
					plt.plot(self.x_vec, trace)
					plt.fill_between(self.x_vec, trace+float(self.span)/2, trace-float(self.span)/2, alpha=0.5)
				except Exception as m:
					print 'invalid trace...skip'
			plt.axhspan(self.y_vec[0], self.y_vec[-1], facecolor='0.5', alpha=0.5)
			plt.show()
		else:
			print 'No trace generated.'


	def measure_1D(self):
	
		global vna
		global mw_src1
	
		if self.x_set_obj == None:
			print 'axes parameters not properly set...aborting'
			return
			
		qt.mstart()
		vna.get_all()
		#ttip.get_temperature()

		nop = vna.get_nop()
		nop_avg = vna.get_averages()
		
		bandwidth = vna.get_bandwidth()
		t_point = nop / bandwidth * nop_avg
		
		freq_points = vna.get_freqpoints()

		data = qt.Data(name=('vna_' + self.x_coordname))
		data.add_coordinate(self.x_coordname)
		#data.add_coordinate('Frequency')

		if self.comment:
			data.add_comment(self.comment)
		
		for i in range(1,nop+1):
			data.add_value(('Point %i Amp' %i))
		for i in range(1,nop+1):
			data.add_value(('Point %i Pha' %i))

		data.create_file()

		plot_amp = qt.Plot2D(data, name='Amplitude', coorddim=0, valdim=int(nop/2)+1)
		plot_pha = qt.Plot2D(data, name='Phase', coorddim=0, valdim=nop+int(nop/2)+1)
		#plot_amp2d = qt.Plot3D(data, name='Amplitude 2D', coorddims=(0,1), valdim=int(nop/2)+1, style=qt.Plot3D.STYLE_IMAGE)
		#plot_amp.set_palette('bluewhitered')

		self.x_set_obj(self.x_vec[0])

		'''
		now_stamp = 0
		now_steps = np.size(x_vec)
		now1 = time.time()
		'''
		p = Progress_Bar(len(self.x_vec))

		#Main Measurement Loop
		try:
			for x in self.x_vec:
				#print "set x value to " + str(x)
				self.x_set_obj(x)
				sleep(self.tdx)
				
				vna.avg_clear()
				sleep(vna.get_sweeptime_averages())

				#print 'measure'
				data_amp,data_pha = vna.get_tracedata()

				dat = []
				dat = np.append(x,data_amp)
				dat = np.append(dat,data_pha)
				data.add_data_point(*dat)

				qt.msleep()

				'''
				now_stamp += 1
				if now_stamp==5:
					now2 = time.time()
					t = (now2-now1)/5
					left = (t*now_steps/60/60);
					if left < 1:
						print('Time left: %f min' %(left*60))
					else:
						print('Time left: %f h' %(left))
				'''
				p.iterate()
		finally:
			plot_amp.save_png()
			plot_amp.save_gp()
			plot_pha.save_png()
			plot_pha.save_gp()
			
			data.close_file()
			qt.mend()

	def measure_1D2(self):

		global vna
		global mw_src1
	
		if self.x_set_obj == None:
			print 'axes parameters not properly set...aborting'
			return
	
		qt.mstart()
		vna.get_all()

		nop = vna.get_nop()
		nop_avg = vna.get_averages()
		bandwidth = vna.get_bandwidth()
		t_point = nop / bandwidth * nop_avg
		freqpoints = vna.get_freqpoints()

		data = qt.Data(name=('vna_sweep1D2_' + self.x_coordname))
		data.add_coordinate(self.x_coordname)
		data.add_coordinate('Frequency')
		data.add_value('Amplitude')
		data.add_value('Phase')

		if self.comment:
			data.add_comment(self.comment)

		data.create_file()

		if self.plotlive:
			plot_amp = qt.Plot3D(data, name='Amplitude 2D2', coorddims=(0,1), valdim=2, style=qt.Plot3D.STYLE_IMAGE)
			plot_amp.set_palette('bluewhitered')
			plot_pha = qt.Plot3D(data, name='Phase 2D2', coorddims=(0,1), valdim=3, style=qt.Plot3D.STYLE_IMAGE)
			plot_pha.set_palette('bluewhitered')

		self.x_set_obj(self.x_vec[0]) #In case for currentsweep go to starting point

		'''
		now_stamp = 0
		now_steps = np.size(x_vec)
		now1 = time.time()
		'''
		p = Progress_Bar(len(self.x_vec))

		try:
			#Main Measurement Loop
			for x in self.x_vec:
				self.x_set_obj(x)
				sleep(self.tdx)
				vna.avg_clear()
				sleep(vna.get_sweeptime_averages())
				data_amp,data_pha = vna.get_tracedata()
				dat = []
				dat = np.append([x*np.ones(nop)],[freqpoints], axis = 0)
				dat = np.append(dat,[data_amp],axis = 0)
				dat = np.append(dat,[data_pha],axis = 0)
				data.add_data_point(*dat)

				data.new_block()
				qt.msleep()

				'''
				now_stamp += 1
				if now_stamp==5:
					now2 = time.time()
					t = (now2-now1)/5
					left = (t*now_steps/60/60);
					if left < 1:
						print('Time left: %f min ' %(left*60))
					else:
						print('Time left: %f h ' %(left))
				'''
				p.iterate()
		finally:
			if not self.plotlive:
				plot_amp = qt.Plot3D(data, name='Amplitude 2D2', coorddims=(0,1), valdim=2, style=qt.Plot3D.STYLE_IMAGE)
				plot_amp.set_palette('bluewhitered')
				plot_pha = qt.Plot3D(data, name='Phase 2D', coorddims=(0,1), valdim=3, style=qt.Plot3D.STYLE_IMAGE)
				plot_pha.set_palette('bluewhitered')
				plot_amp.update()
				plot_pha.update()
				
			plot_amp.save_png()
			plot_amp.save_gp()
			plot_pha.save_png()
			plot_pha.save_gp()

			data.close_file()
			qt.mend()
			
	def measure_2D(self):
		
		'''
		measure method to perform the measurement according to landscape, if set
		self.span is the range (in units of the vertical plot axis) data is taken around the specified funtion(s) 
		'''

		global vna
		global mw_src1
		
		if self.x_set_obj == None or self.y_set_obj == None:
			print 'axes parameters not properly set...aborting'
			return
		
		if self.landscape != None:
			center_freqs = np.array(self.landscape).T
		else:
			center_freqs = []   #load default sequence
			for i in range(len(self.x_vec)):
				center_freqs.append([0])
		'''
		prepare an array of length len(x_vec), each segment filled with an array being the number of present traces (number of functions)
		'''

		qt.mstart()
		vna.get_all()
		#ttip.get_temperature()

		nop = vna.get_nop()
		nop_avg = vna.get_averages()
		bandwidth = vna.get_bandwidth()
		t_point = nop / bandwidth * nop_avg

		data = qt.Data(name=('vna_' + self.x_coordname + self.y_coordname))
		data.add_coordinate(self.x_coordname)
		data.add_coordinate(self.y_coordname)

		if self.comment:
			data.add_comment(self.comment)

		for i in range(1,nop+1):
			data.add_value(('Point %i Amp' %i))
		for i in range(1,nop+1):
			data.add_value(('Point %i Pha' %i))

		data.create_file()

		if(self.plotlive):
			if(self.plot3D):
				plot_amp = qt.Plot3D(data, name='Amplitude', coorddims=(0,1), valdim=int(nop/2)+2, style=qt.Plot3D.STYLE_IMAGE)
				plot_amp.set_palette('bluewhitered')
				plot_pha = qt.Plot3D(data, name='Phase', coorddims=(0,1), valdim=int(nop/2)+2+nop, style=qt.Plot3D.STYLE_IMAGE)
				plot_pha.set_palette('bluewhitered')
			else:
				plot_amp = qt.Plot2D(data, name='Amplitude', coorddim=1, valdim=int(nop/2)+2)
				plot_pha = qt.Plot2D(data, name='Phase', coorddim=1, valdim=int(nop/2)+2+nop)

		'''
		now1 = time.time()
		x_it = 0
		'''
		p = Progress_Bar(len(self.x_vec)*len(self.y_vec))

		try:
			for i in range(len(self.x_vec)):
				'''
				if x_it == 1:
					now2 = time.time()
					t = (now2-now1)
					left = (t*np.size(self.x_vec)/60/60);
					if left < 1:
						print('Time left: %f min' %(left*60))
					else:
						print('Time left: %f h' %(left))
				'''
				
				self.x_set_obj(self.x_vec[i])
				sleep(self.tdx)
				#x_it+=1

				for y in self.y_vec:
					if (np.min(np.abs(center_freqs[i]-y*np.ones(len(center_freqs[i])))) > self.span/2.) and self.landscape != None:   #if point is not of interest (not close to one of the functions)
						data_amp = np.zeros(int(nop))
						data_pha = np.zeros(int(nop))   #fill with zeros
					else:
						self.y_set_obj(y)
						sleep(self.tdy)
						sleep(vna.get_sweeptime_averages())
						data_amp,data_pha = vna.get_tracedata()

					dat = np.append(self.x_vec[i],y)
					dat = np.append(dat,data_amp)
					dat = np.append(dat,data_pha)
					data.add_data_point(*dat)  # _one_

					qt.msleep()
					p.iterate()

				data.new_block()
		finally:
			if(not self.plotlive):
				if(self.plot3D):
					plot_amp = qt.Plot3D(data, name='Amplitude', coorddims=(0,1), valdim=int(nop/2)+2, style=qt.Plot3D.STYLE_IMAGE)
					plot_amp.set_palette('bluewhitered')
					plot_pha = qt.Plot3D(data, name='Phase', coorddims=(0,1), valdim=int(nop/2)+2+nop, style=qt.Plot3D.STYLE_IMAGE)
					plot_pha.set_palette('bluewhitered')
				else:
					plot_amp = qt.Plot2D(data, name='Amplitude', coorddim=1, valdim=int(nop/2)+2)
					plot_pha = qt.Plot2D(data, name='Phase', coorddim=1, valdim=int(nop/2)+2+nop)

			plot_amp.save_png()
			plot_amp.save_gp()
			plot_pha.save_png()
			plot_pha.save_gp()

			data.close_file()

			qt.mend()

