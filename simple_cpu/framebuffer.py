from simple_cpu.devices import BaseCPUDevice
from simple_cpu.memory import MemoryMap
import vgaconsole, pygame

class Framebuffer(MemoryMap):
    def __init__(self, vgabuf):
        super(Framebuffer, self).__init__(0x1)
        self.mem = vgabuf
        self.size = 4000
        self.__read = True
        self.__write = True
        self.__execute = False

class VGAConsoleDevice(BaseCPUDevice):
    """ This virtual device will allow you to easily interface with my VGAConsole project. """
    ports = [7777]
    def start(self):
        """ This will initialize the actual framebuffer device. """
        pygame.display.init()
        self.screen = pygame.display.set_mode((640,400),0,8)
        pygame.display.set_caption('Simple CPU Simulator framebuffer')
        self.vga = vgaconsole.VGAConsole(self.screen)
        self.cpu.mem.add_map(0xc, Framebuffer(self.vga.vgabuf))
        self.vga.foreground = 7
        self.vga.background = 0
        self.vga.draw()
        pygame.display.update()
    def stop(self):
        pygame.quit()
    def cycle(self):
        vgaconsole.clock.tick(30)
        events = pygame.event.get()
        for e in events:
            if e.type == vgaconsole.QUIT:
                pygame.quit()
                self.cpu.running = False
                return
            else:
                self.vga.handle_event(e)
        self.vga.draw()
        pygame.display.update()
