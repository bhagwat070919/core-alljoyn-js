#!/usr/bin/env python
# Copyright AllSeen Alliance. All rights reserved.
#
# Permission to use, copy, modify, and/or distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
# ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
# WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
# ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
# OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
import sys
import re

major_version = sys.version_info[0]

if major_version < 3:
    from Tkinter import *
    from tkMessageBox import *
    from tkFileDialog import *
    import Queue
else:
    from tkinter import *
    from tkinter import messagebox as tm
    import queue as Queue
    from tkinter import filedialog
import os

import AJSConsole

printMsgFilter = 'off'
notifMsgFilter = 'off'
debugMsgFilter = 'off'
numBreakpoints = 0
selectedBreakpoint = -1
selectedLocal = -1
currentFile = ''
varSelected = ''

help_message = 'This Python debugger is used to debug AllJoyn.js applications\n\
                \rOn the left side of the GUI you have buttons to control the debug target\n\
                \rStep Into: Step into a function\n\
                \rStep Over: Step over a function or line of code\n\
                \rStep Out: Step out of the current scope\n\
                \rPause: Pause execution (if the target is running)\n\
                \rResume: Resume execution (if the target is paused)\n\
                \rAttach: Attach to a debug target\n\
                \rDetach: Detach from a debug target\n\
                \rRefresh: Refresh local variables, breakpoints, or the stack trace\n\
                \rClose: Exit the debugger\n\
                \rOn the right side there is a window for local variables. Here you can\
                see the variables name and value. If the variable has a complex type (pointer, object, buffer) it will\
                just show the value of the first element in that variable\n\
                \rBelow variables is a list of breakpoints. Under the breakpoints is a text box where you can add\
                breakpoints. To do this type the name of the script followed by the line you wish to add the\
                breakpoint at. For example: "my_script.js 15". To delete a breakpoint use the text box directly to \
                the right of where you added them. Simple put the index of the breakpoint you wish to delete.'

# Turn on and off editing for each window
def enableEditing(window, onoff):
    if window == 'source':
        if onoff == 'on':
            dbg.RightFrame.SourceView.config(state=NORMAL)
        else:
            dbg.RightFrame.SourceView.config(state=DISABLED)
    elif window == 'locals':
        if onoff == 'on':
            dbg.LocalsFrame.LocalVars.config(state=NORMAL)
        else:
            dbg.LocalsFrame.LocalVars.config(state=DISABLED)
    elif window == 'breakpoints':
        if onoff == 'on':
            dbg.BreakFrame.Breakpoints.config(state=NORMAL)
        else:
            dbg.BreakFrame.Breakpoints.config(state=DISABLED)
    elif window == 'stack':
        if onoff == 'on':
            dbg.BreakFrame.StackTrace.config(state=NORMAL)
        else:
            dbg.BreakFrame.StackTrace.config(state=DISABLED)
    elif window == 'console':
        if onoff == 'on':
            dbg.BottomFrame.ConsoleWindow.config(state=NORMAL)
        else:
            dbg.BottomFrame.ConsoleWindow.config(state=DISABLED)

# Get the current line number
def getLine():
    return AJSConsole.GetLine()

# Populate the window title with the debug version
def updateVersion():
    version = AJSConsole.GetDebugVersion()
    dbg.master.title("Debugger GUI Version: " + version)

# Updates and highlights the current line in the source code viewer 
def lineUpdate():
    enableEditing('source', 'on')
    dbg.RightFrame.SourceView.tag_delete("Line")
    dbg.RightFrame.SourceView.tag_add("Line", str(getLine())+'.2', str(getLine())+'.end')
    dbg.RightFrame.SourceView.tag_config("Line", background="yellow")
    enableEditing('source', 'off')

# Updates local variables and values
def localUpdate():
    global selectedLocal
    state = AJSConsole.GetTargetStatus()
    # Cut down on error printing and ensure we can get local variables
    if state != 2 and state != 3:
        locals = AJSConsole.GetLocals()
        if type(locals) != type(None):
            enableEditing('locals', 'on')
            dbg.LocalsFrame.LocalVars.delete('0.0', END)
            for i in range(len(locals)):
                dbg.LocalsFrame.LocalVars.insert(str(i+1)+'.0', locals[i][0] + "\t" + str(locals[i][1])+ "\n")
                if selectedLocal != -1:
                    if i + 1 == selectedLocal:
                        dbg.LocalsFrame.LocalVars.tag_delete("LocalSelection")
                        dbg.LocalsFrame.LocalVars.tag_add("LocalSelection", str(selectedLocal)+'.0', str(selectedLocal)+'.end')
                        dbg.LocalsFrame.LocalVars.tag_config("LocalSelection", background="yellow")
            enableEditing('locals', 'off')
        else:
            enableEditing('locals', 'on')
            dbg.LocalsFrame.LocalVars.delete('0.0', END)
            enableEditing('locals', 'off')

# Updates the current stack trace
def stackUpdate():
    state = AJSConsole.GetTargetStatus()
    if state != 2 and state != 3:
        stacktrace = AJSConsole.GetStacktrace()
        if type(stacktrace) != type(None):
            enableEditing('stack', 'on')
            dbg.BreakFrame.StackTrace.delete('0.0', END)
            for i in range(len(stacktrace)):
                dbg.BreakFrame.StackTrace.insert(str(i+1)+'.0', str(i+1) + ": " + stacktrace[i][1] + "\tLine: " + str(stacktrace[i][2]) + "\tPC: " + str(stacktrace[i][3]) + "\n")
            enableEditing('stack', 'off')

# Updates the current breakpoint list
def breakpointUpdate():
    global numBreakpoints
    global selectedBreakpoint
    state = AJSConsole.GetTargetStatus()
    # Can be in running, paused, or busy state
    if state != 3:
        breakpoints = AJSConsole.GetBreakpoints()
        if type(breakpoints) != type(None):
            enableEditing('breakpoints', 'on')
            dbg.BreakFrame.Breakpoints.delete('0.0', END)
            numBreakpoints = len(breakpoints)
            for i in range(len(breakpoints)):
                if type(breakpoints[i][0]) != type(None) and type(breakpoints[i][1]) != type(None):
                    # For each breakpoint, insert it into the window
                    dbg.BreakFrame.Breakpoints.insert(str(i+1)+'.0', str(i) + ": " + breakpoints[i][0] + "\t" + str(breakpoints[i][1]) + "\n")
                    if i == selectedBreakpoint:
                        dbg.BreakFrame.Breakpoints.tag_delete("Selection")
                        dbg.BreakFrame.Breakpoints.tag_add("Selection", str(selectedBreakpoint)+'.0', str(selectedBreakpoint)+'.end')
                        dbg.BreakFrame.Breakpoints.tag_config("Selection", background="yellow")
                # For each breakpoint, highlight the line number red in the source window
                line = breakpoints[i][1]
                dbg.RightFrame.SourceView.tag_delete("BPView."+str(i))
                dbg.RightFrame.SourceView.tag_add("BPView."+str(i), str(line)+'.0', str(line)+'.2')
                dbg.RightFrame.SourceView.tag_config("BPView."+str(i), background="red")
            enableEditing('breakpoints', 'off')

# Updates current line, local variables, stack trace, and breakpoints
def globalUpdate():
    state = AJSConsole.GetTargetStatus()
    lineUpdate()
    if state != 2 and state != 3:
        localUpdate()
        stackUpdate()

# Recursive updater function, called every 500ms
def globalUpdater():
    globalUpdate()
    dbg.after(500, globalUpdater)

def stepInto():
    AJSConsole.StepInto()
    globalUpdate()

def stepOut():
    AJSConsole.StepOut()
    globalUpdate()

def stepOver():
    AJSConsole.StepOver()
    globalUpdate()

# Add a breakpoint
def addBreakpoint():
    text = dbg.BreakFrame.AddBreakpoints.get('0.0', END)
    enableEditing('breakpoints', 'on')
    dbg.BreakFrame.AddBreakpoints.delete('0.0', END);
    AJSConsole.AddBreakpoint(text)
    line = ''.join(text).split(' ')[1]
    dbg.DebugNotification("Breakpoint added at line " + str(line))
    breakpointUpdate()
    enableEditing('breakpoints', 'off')

def text_is_number(t):
    try:
        int(t)
        return True
    except ValueError:
        return False

def does_index_exist(list, index):
    try:
        tmp = list[index]
        return True
    except IndexError:
        return False

def localSelectHandler(event):
    global varSelected
    line_start = dbg.RightFrame.SourceView.index("@%s,%s linestart" % (event.x, event.y))
    line_start = line_start.split('.')[0]
    text = dbg.RightFrame.SourceView.get(str(line_start) + '.0', str(line_start) + '.end')
    index = text.find('var')
    if index != -1:
        # There is a tab after the line numbers so add 4 (spaces) to the index
        index = index + 4; 
        # Find the variables string length
        text = re.findall(r"[\w']+", text)
        for i in range(len(text)):
            if str(text[i]) == 'var':
                var = str(text[i + 1])
                varLen = len(str(text[i + 1]))
        if var == varSelected:
            dbg.RightFrame.SourceView.tag_config("cur_var", background="white")
        else:
            dbg.RightFrame.SourceView.tag_delete("cur_var")
            dbg.RightFrame.SourceView.tag_add("cur_var", str(line_start) + '.' + str(index - 4), str(line_start) + '.' + str(index + varLen))
            dbg.RightFrame.SourceView.tag_config("cur_var", background="cyan")
            varSelected = var


# Triggered by double left click (add breakpoint)
def sourceViewEventHandler(event):
    global currentFile
    global numBreakpoints
    # Get the line of the requested breakpoint addition
    line_start = dbg.RightFrame.SourceView.index("@%s,%s linestart" % (event.x, event.y))
    line_start = line_start.split('.')[0]
    if numBreakpoints == 0:
        AJSConsole.AddBreakpoint(currentFile + ' ' + line_start)
        dbg.DebugNotification("Breakpoint added at line " + line_start)
        breakpointUpdate()
    else:
        canAdd = True
        for i in range(numBreakpoints):
            line = dbg.BreakFrame.Breakpoints.get(str(i+1) + '.0', str(i+1) + '.end')
            if does_index_exist(line.split('\t'), 1):
                line = line.split('\t')[1]
                # Check that the breakpoint doesn't already exist
                if line == line_start:
                    canAdd = False
                    break
        if canAdd:
            AJSConsole.AddBreakpoint(currentFile + ' ' + line_start)
            dbg.DebugNotification("Breakpoint added at line " + line_start)
            breakpointUpdate()

def localsEventHandler(event):
    global selectedLocal
    state = AJSConsole.GetTargetStatus()
    if state != 3:
        enableEditing('locals', 'on')
        locals = AJSConsole.GetLocals()
        if type(locals) != type(None):
            for i in range(len(locals)):
                index = dbg.LocalsFrame.LocalVars.index("@%s,%s linestart" % (event.x, event.y))
                index = index.split('.')[0]
                if selectedLocal == i + 1:
                    dbg.LocalsFrame.LocalVars.tag_delete("LocalSelection")
                    dbg.LocalsFrame.LocalVars.tag_add("LocalSelection", index+'.0', index+'.end')
                    dbg.LocalsFrame.LocalVars.tag_config("LocalSelection", background="white")
                    selectedLocal = -1
                    break
                if index == str(i + 1):
                    dbg.LocalsFrame.LocalVars.tag_delete("LocalSelection")
                    dbg.LocalsFrame.LocalVars.tag_add("LocalSelection", index+'.0', index+'.end')
                    dbg.LocalsFrame.LocalVars.tag_config("LocalSelection", background="yellow")
                    selectedLocal = int(index)
                    break
        enableEditing('locals', 'off')

def breakpointEventHandler(event):
    global selectedBreakpoint
    global numBreakpoints

    enableEditing('breakpoints', 'on')
    line_start = dbg.BreakFrame.Breakpoints.index("@%s,%s linestart" % (event.x, event.y))
    line_start = line_start.split('.')[0]
    selection = dbg.BreakFrame.Breakpoints.get(line_start + '.0', line_start + '.end')
    selection = selection.split(':')[0]
    selection = str(selection)
    for i in range(numBreakpoints):
        if text_is_number(selection):
            if selection == str(selectedBreakpoint):
                dbg.BreakFrame.Breakpoints.tag_delete("Selection")
                dbg.BreakFrame.Breakpoints.tag_add("Selection", line_start+'.0', line_start+'.end')
                dbg.BreakFrame.Breakpoints.tag_config("Selection", background="white")
                selectedBreakpoint = -1
                break
            else:
                if text_is_number(selection):
                    dbg.BreakFrame.Breakpoints.tag_delete("Selection")
                    dbg.BreakFrame.Breakpoints.tag_add("Selection", line_start+'.0', line_start+'.end')
                    dbg.BreakFrame.Breakpoints.tag_config("Selection", background="yellow")
                    selectedBreakpoint = int(selection)
                break
    enableEditing('breakpoints', 'off')

# Remove a breakpoint
def delBreakpoint():
    global selectedBreakpoint
    global numBreakpoints
    if selectedBreakpoint > -1:
        text = dbg.BreakFrame.Breakpoints.get(str(selectedBreakpoint + 1) + '.0', str(selectedBreakpoint + 1) + '.end')
        # Get the file and line from the selected text
        line = text.split(' ')[1].split('\t')[1]
        file = text.split(' ')[1].split('\t')[0]
        index = text.split(':')[0]
        text = file + ' ' + line
        for i in range(numBreakpoints):
            # Remove the red highlight from the source window
            dbg.RightFrame.SourceView.tag_delete("BPView."+str(i))
            dbg.RightFrame.SourceView.tag_add("BPView."+str(i), str(line)+'.0', str(line)+'.2')
            dbg.RightFrame.SourceView.tag_config("BPView."+str(i), background="white")
        # Send the remove breakpoint command
        AJSConsole.DelBreakpoint(index)
        # Update
        breakpointUpdate()

# Pause the debugger
def pause():
    AJSConsole.Pause()

# Resume the debugger (run/continue)
def resume():
    AJSConsole.Resume()

# Gets and updates the source code window with the current script thats running
def getScript():
    script = AJSConsole.GetScript()
    if len(script) > 0:
        enableEditing('source', 'on')
        dbg.RightFrame.SourceView.delete('0.0', END)
        dbg.RightFrame.SourceView.insert('0.0', AJSConsole.GetScript())
        # Insert line numbers into the script
        for i in range(1, int(dbg.RightFrame.SourceView.index('end').split('.')[0])):
            dbg.RightFrame.SourceView.insert(str(i)+'.0', str(i)+':\t')
        lineUpdate()
        enableEditing('source', 'off')
    else:
        dbg.DebugNotification("No script found on target, please install a script")

def detach():
    AJSConsole.Detach()
    breakpointUpdate()
    #viewBreakpointUpdate()

def attach():
    AJSConsole.Attach()

def showHelp():
    showinfo('Debugger GUI Help', help_message)

def install():
    options = {}
    options['initialdir'] = os.getcwd()
    full_filename = askopenfilename(**options)
    if type(full_filename) == str and full_filename != '':
        # Check if the debugger is detached
        if AJSConsole.GetTargetStatus() != 3:
            AJSConsole.Detach()
        f = open(full_filename, 'r')
        f.seek(os.SEEK_SET, os.SEEK_END)
        length = f.tell()
        f.seek(os.SEEK_SET, 0)
        data = f.read()
        filename = full_filename.split('/')
        AJSConsole.Install(filename[len(filename) - 1], data)
        AJSConsole.Attach()
        getScript()

def eval():
    status = AJSConsole.GetTargetStatus()
    text = dbg.BottomFrame.EvalTextBox.get('0.0', END)
    if status != 3:
        result = AJSConsole.DebugEval(text)
    else:
        result = AJSConsole.DebugEval(text)
    if type(result) != NoneType:
            dbg.EvalNotification(`result`)
    # In case we changed a local variable update locals
    localUpdate();

def putVar():
    global selectedLocal
    global varSelected
    state = AJSConsole.GetTargetStatus()
    text = dbg.LocalsFrame.PutVar.get('0.0', END).strip('\n')
    if selectedLocal != -1 and text != '\n':
        var = dbg.LocalsFrame.LocalVars.get(str(selectedLocal) + '.0', str(selectedLocal) + '.end')
        var = var.split('\t')[0]
        if state != 3:
            AJSConsole.DebugEval(var + '=' + text);
        localUpdate()
    elif varSelected != '':
        if state != 3:
            if not text_is_number(text):
                text = '"' + text + '"'
            AJSConsole.DebugEval(varSelected + '=' + text)
            dbg.RightFrame.SourceView.tag_config("cur_var", background="white")
            dbg.DebugNotification(str("Variable: " + varSelected + " changed to " + text))
            varSelected = ''
    # In case we changed a local variable update locals
    localUpdate();

def closeDebugger():
    AJSConsole.Detach()
    quit()

root = Tk()

class DebugGUI(Frame):

    def __init__(self, master=None):
        Frame.__init__(self, master)

        self.inputq = Queue.Queue()

        self.master.title("Debugger GUI")

        self.master.rowconfigure(0, weight=1)

        # Left frame contains all the buttons
        self.LeftFrame = Frame(master)
        self.LeftFrame.grid(row = 0, column = 0, rowspan = 6, columnspan = 1, sticky = N)
        self.LeftFrame.StepIn = Button(self.LeftFrame, text="Step Into", command=stepInto, width=10, height=2)
        self.LeftFrame.StepIn.grid(row=0, column=0, sticky=W+N)
        self.LeftFrame.StepOver = Button(self.LeftFrame, text="Step Over", command=stepOver, width=10, height=2)
        self.LeftFrame.StepOver.grid(row=1, column=0, sticky=W+N)
        self.LeftFrame.StepOut = Button(self.LeftFrame, text="Step Out", command=stepOut, width=10, height=2)
        self.LeftFrame.StepOut.grid(row=2, column=0, sticky=W+N)
        self.LeftFrame.Pause = Button(self.LeftFrame, text="Pause", command=pause, width=10, height=2)
        self.LeftFrame.Pause.grid(row=3, column=0, sticky=W+N)
        self.LeftFrame.Resume = Button(self.LeftFrame, text="Resume", command=resume, width=10, height=2)
        self.LeftFrame.Resume.grid(row=4, column=0, sticky=W+N)
        self.LeftFrame.Attach = Button(self.LeftFrame, text="Attach", command=attach, width=10, height=2)
        self.LeftFrame.Attach.grid(row=5, column=0, sticky=W+N)
        self.LeftFrame.Detach = Button(self.LeftFrame, text="Detach", command=detach, width=10, height=2)
        self.LeftFrame.Detach.grid(row=6, column=0, sticky=W+N)
        self.LeftFrame.Refresh = Button(self.LeftFrame, text="Refresh", command=globalUpdate, width=10, height=2)
        self.LeftFrame.Refresh.grid(row=7, column=0, sticky=W+N)
        self.LeftFrame.Help = Button(self.LeftFrame, text="Install...", command=install, width=10, height=2)
        self.LeftFrame.Help.grid(row=8, column=0, sticky=W+N)
        self.LeftFrame.Close = Button(self.LeftFrame, text="Close", command=closeDebugger, width=10, height=2)
        self.LeftFrame.Close.grid(row=9, column=0, sticky=W+N)
        self.LeftFrame.Help = Button(self.LeftFrame, text="Help", command=showHelp, width=10, height=2)
        self.LeftFrame.Help.grid(row=10, column=0, sticky=W+N)

        # RightFrame contains the source code text box
        self.RightFrame = Frame(master)
        self.RightFrame.grid(row = 0, column = 1, rowspan = 6, columnspan = 4, sticky = W+E+N+S)
        self.RightFrame.SourceView = Text(self.RightFrame, width=80, height=35)
        self.RightFrame.SourceView.grid(row=0, column=1, rowspan=11, columnspan=3, sticky=W+E+N+S)
        self.RightFrame.SourceView.insert('1.0', "No source loaded yet")
        self.RightFrame.SourceView.tag_add("Line", str(getLine())+'.0', str(getLine())+'.end')
        self.RightFrame.SourceView.config(wrap=NONE, state=DISABLED)
        self.RightFrame.SourceView.bind('<Double-1>', sourceViewEventHandler)
        self.RightFrame.SourceView.bind('<Button-1>', localSelectHandler)

        # LocalsFrame contains the local variables
        self.LocalsFrame = Frame(master)
        self.LocalsFrame.grid(row = 0, column = 5, rowspan = 2, columnspan = 2, sticky = W+E+N+S)
        self.LocalsFrame.LocalVars = Text(self.LocalsFrame, width=60, height=8)
        self.LocalsFrame.LocalVars.grid(row=0, column=5, rowspan=1, columnspan=1, sticky=N)
        self.LocalsFrame.LocalVars.bind('<Button-1>', localsEventHandler)
        self.LocalsFrame.LocalVars.config(state=DISABLED)
        self.LocalsFrame.PutVarButton = Button(self.LocalsFrame, text="PutVar", width=10, height=1, command=putVar)
        self.LocalsFrame.PutVarButton.grid(row=2, column=5, sticky=W)
        self.LocalsFrame.PutVar = Text(self.LocalsFrame, width=45, height=2)
        self.LocalsFrame.PutVar.grid(row=2, column=5, rowspan=1, columnspan=1, sticky=E)

        # BreakFrame contains the breakpoint viewer, breakpoint add/delete, and the stack trace viewer
        self.BreakFrame = Frame(master)
        self.BreakFrame.grid(row = 3, column = 5, rowspan = 1, columnspan = 1, sticky = W+E+N+S)
        self.BreakFrame.Breakpoints = Text(self.LocalsFrame, width=60, height=10)
        self.BreakFrame.Breakpoints.grid(row=3, column=5, rowspan=2, columnspan=1, sticky=N)
        self.BreakFrame.Breakpoints.insert('0.0', "No breakpoints")
        self.BreakFrame.Breakpoints.config(state=DISABLED)
        self.BreakFrame.Breakpoints.bind('<Button-1>', breakpointEventHandler)

        self.BreakFrame.AddBreakpoints = Text(self.LocalsFrame, width=60, height=2)
        self.BreakFrame.AddBreakpoints.grid(row=5, column=5, rowspan=1, columnspan=1, sticky=N+W)
        self.BreakFrame.AddBreakButton = Button(self.LocalsFrame, text="Add Breakpoint", command=addBreakpoint)
        self.BreakFrame.AddBreakButton.grid(row=6, column=5, sticky=W+N)

        self.BreakFrame.DelBreakpointsButton = Button(self.LocalsFrame, text="Delete", command=delBreakpoint)
        self.BreakFrame.DelBreakpointsButton.grid(row=6, column=5, sticky=N+E)

        self.BreakFrame.StackTrace = Text(self.LocalsFrame, width=60, height=10)
        self.BreakFrame.StackTrace.grid(row=7, column=5, sticky=N+W)
        self.BreakFrame.StackTrace.config(state=DISABLED)

        # BottomFrame contains the console window for viewing Prints, Alerts and debug messages
        self.BottomFrame = Frame(master)
        self.BottomFrame.grid(row=11, column=1, rowspan=1, columnspan=7, sticky=N)
        self.BottomFrame.ConsoleWindow = Text(self.BottomFrame, width=140, height=10)
        self.BottomFrame.ConsoleWindow.grid(row=13, column=1, columnspan=5, sticky=N)
        self.BottomFrame.ConsoleWindow.insert('0.0', 'Text Console Window\n')

        self.BottomFrame.EvalButton = Button(self.BottomFrame, text="Eval", width=10, height=1, command=eval)
        self.BottomFrame.EvalButton.grid(column=1, row=11)
        self.BottomFrame.EvalTextBox = Text(self.BottomFrame, width=125, height=2)
        self.BottomFrame.EvalTextBox.grid(row=11, column=2, columnspan=5, sticky=N)

        # BottomButtonFrams contains the console window filter buttons. These filter in/out
        # Print, Alert, and Debug messages.
        self.BottomButtonFrame = Frame(master)
        self.BottomButtonFrame.grid(row=11, column=0, rowspan=2, columnspan=1, sticky=N)
        self.BottomButtonFrame.CtrlLabel = Label(self.BottomButtonFrame, text="Filter (On/Off):")
        self.BottomButtonFrame.CtrlLabel.grid(row=12, column=0, sticky=W+N)
        self.BottomButtonFrame.PrintOnOff = Button(self.BottomButtonFrame, text="Print", width=10, height=1, command=self.PrintMode)
        self.BottomButtonFrame.PrintOnOff.grid(row=13, column=0, sticky=W+N)
        self.BottomButtonFrame.PrintOnOff.config(relief=SUNKEN)
        self.BottomButtonFrame.NotifOnOff = Button(self.BottomButtonFrame, text="Notifcation", width=10, height=1, command=self.NotifPrintMode)
        self.BottomButtonFrame.NotifOnOff.grid(row=14, column=0, sticky=W+N)
        self.BottomButtonFrame.NotifOnOff.config(relief=SUNKEN)
        self.BottomButtonFrame.DebugOnOff = Button(self.BottomButtonFrame, text="Debug", width=10, height=1, command=self.DebugPrintMode)
        self.BottomButtonFrame.DebugOnOff.grid(row=15, column=0, sticky=W+N)
        self.BottomButtonFrame.DebugOnOff.config(relief=SUNKEN)

        # This checks for notifications, prints, alerts, and debug messages from the console
        self.master.after(500, self.PollQueue)

    # Turn on/off Prints in the console window
    def PrintMode(self):
        global printMsgFilter
        current = self.BottomButtonFrame.PrintOnOff.cget('relief')
        if current == 'sunken':
            printMsgFilter = 'on'
            self.BottomButtonFrame.PrintOnOff.config(relief=RAISED)
        elif current == 'raised':
            printMsgFilter = 'off'
            self.BottomButtonFrame.PrintOnOff.config(relief=SUNKEN)

    # Turn on/off notification prints in the console window
    def NotifPrintMode(self):
        global notifMsgFilter
        current = self.BottomButtonFrame.NotifOnOff.cget('relief')
        if current == 'sunken':
            notifMsgFilter = 'on'
            self.BottomButtonFrame.NotifOnOff.config(relief=RAISED)
        elif current == 'raised':
            notifMsgFilter = 'off'
            self.BottomButtonFrame.NotifOnOff.config(relief=SUNKEN)

    # Turn on/off debug prints in the console window
    def DebugPrintMode(self):
        global debugMsgFilter
        current = self.BottomButtonFrame.DebugOnOff.cget('relief')
        if current == 'sunken':
            debugMsgFilter = 'on'
            self.BottomButtonFrame.DebugOnOff.config(relief=RAISED)
        elif current == 'raised':
            debugMsgFilter = 'off'
            self.BottomButtonFrame.DebugOnOff.config(relief=SUNKEN)

    # Input a message into the queue
    def QueueInput(self, item):
        self.inputq.put(item, False)

    # Check for a message in the queue
    def PollQueue(self, *args):
        while True:
            try:
                item = self.inputq.get(False)
            except Queue.Empty:
                break

            self.AJInput(item)

        self.master.after(50, self.PollQueue)

    # Handle a message/notification from the console
    def AJInput(self, item):
        cbtype, args = item

        if cbtype == "Print":
            self.Print(args)
        elif cbtype == "Alert":
            self.Alert(args)
        elif cbtype == "Notification":
            self.Notification(args)
        elif cbtype == "DebugNotification":
            self.DebugNotification(args)

    # Update the console window with a Print message
    def Print(self, arg):
        if printMsgFilter == 'off':
            enableEditing('console', 'on')
            self.BottomFrame.ConsoleWindow.insert(END, "PRINT: " + arg[0] + '\n')
            self.BottomFrame.ConsoleWindow.yview(END)
            enableEditing('console', 'off')

    # Pop up an Alert message
    def Alert(self, arg):
        showinfo('Alert', arg[0])

    # Update the console window with a Notification message
    def Notification(self, args):
        if notifMsgFilter == 'off':
            enableEditing('console', 'on')
            self.BottomFrame.ConsoleWindow.insert(END, "NOTIF: " + repr(args) + '\n')
            self.BottomFrame.ConsoleWindow.yview(END)
            enableEditing('console', 'off')

    # Update the console window with a DebugNotification message
    def DebugNotification(self, args):
        global currentFile
        if args[0][0] == 'S':
            # Make sure this is the proper notification
            currentFile = args[0].split(',')[1].split(' ')[2]
            state = args[0].split(',')[0].split(' ')[1]
            line = args[0].split(',')[3].split(' ')[2]
            enableEditing('source', 'on')
            dbg.RightFrame.SourceView.tag_delete("Line")
            dbg.RightFrame.SourceView.tag_add("Line", line +'.2', line + '.end')
            dbg.RightFrame.SourceView.tag_config("Line", background="yellow")
            enableEditing('source', 'off')
            localUpdate()
            stackUpdate()
            updateVersion()
        if debugMsgFilter == 'off':
            enableEditing('console', 'on')
            self.BottomFrame.ConsoleWindow.insert(END, "DEBUG: " + repr(args) + '\n')
            self.BottomFrame.ConsoleWindow.yview(END)
            enableEditing('console', 'off')

    def EvalNotification(self, args):
        enableEditing('console', 'on')
        self.BottomFrame.ConsoleWindow.insert(END, "EVAL: " + repr(args) + '\n')
        self.BottomFrame.ConsoleWindow.yview(END)
        enableEditing('console', 'off')

# Universal callback for all messages from the console
def callback(cbtype, *args):
    dbg.QueueInput((cbtype, args))

dbg = DebugGUI(master=root)

AJSConsole.SetCallback(callback)
status = AJSConsole.Connect()
if status == 'ER_OK':
    status = AJSConsole.StartDebugger()
    if status == 'ER_OK':
        # Populates the source view window
        getScript()
        dbg.mainloop()
    else:
        showinfo('Failed to start debugger', status)
else:
    showinfo('Failed to connect to debug target', status)



