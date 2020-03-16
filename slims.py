#TechSideOnline.com Webify Sublime Text 3 plugin example

import sublime, sublime_plugin, re, string   #import the required modules

class ZuckerCommand(sublime_plugin.TextCommand): #create Webify Text Command
	def run(self, edit):   #implement run method
		for region in self.view.sel():  #get user selection
			if not region.empty():  #if selection not empty then
				s = self.view.substr(region)  #assign s variable the selected region
				news = s.replace('<', '&lt;')
				news = news.replace('>', '&gt;')
				self.view.replace(edit, region, news) #replace content in view
