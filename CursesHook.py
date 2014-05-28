"""
This python module includes a CPU Hook that enables controlled apps to use the ncurses library.
This is an example of how you might extend the CPU simulator to access the outside world.
"""

from cpu import BaseCPUHook
import curses

class CursesHook(BaseCPUHook):
    opcode = 67
    opname = 'cur'
    stdscr = None
    def cleanup(self):
        if self.stdscr is None:
            return
        self.stdscr.keypad(0)
        curses.echo()
        curses.nocbreak()
        curses.endwin()
        self.stdscr = None
    def hook_1(self):
        if self.stdscr is None:
            self.stdscr = curses.initscr()
            curses.noecho()
            curses.cbreak()
            self.stdscr.keypad(1)
            try:
                curses.start_color()
            except:
                pass
            self.wins = []
            self.style = curses.A_NORMAL
    def hook_2(self):
        if self.stdscr is None:
            return
        self.cpu.mem.push()
        self.cpu.mem.ptr = self.cpu.ax.b
        self.wins.append(curses.newwin(self.cpu.mem.read().b, self.cpu.mem.read().b, self.cpu.mem.read().b, self.cpu.mem.read().b))
        self.cpu.ax.value = len(self.wins)-1
        self.cpu.mem.pop()
    def hook_3(self):
        if self.stdscr is None:
            return
        self.cpu.mem.push()
        self.cpu.mem.ptr = self.cpu.bx.b
        text = self.cpu.mem.readstring()
        self.cpu.mem.pop()
        self.wins[self.cpu.ax.b].addstr(self.cpu.cx.b, self.cpu.dx.b, text, self.style)
    def hook_4(self):
        if self.stdscr is None:
            return
        self.cpu.cx.value = self.wins[self.cpu.ax.b].getch()
    def hook_10(self):
        if self.stdscr is None:
            return
        self.wins[self.cpu.ax.b].idlok(self.cpu.bx.b)
    def hook_11(self):
        if self.stdscr is None:
            return
        self.cpu.mem.push()
        self.cpu.mem.ptr = self.cpu.bx.b
        border = self.cpu.mem.read(8)
        self.wins[self.cpu.ax.b].border(*list(border))
        self.cpu.mem.pop()
    def hook_255(self):
        self.cleanup()
