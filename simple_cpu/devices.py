from simple_cpu.exceptions import InvalidInterrupt, CPUException,\
    MemoryProtectionError
import sys
try:
    import termios
except ImportError:
    termios = None

class BaseCPUDevice(object):
    """
    This is the base class to extend the VM/CPU using virtual I/O ports.
    """
    def __init__(self, cpu):
        self.cpu = cpu
    def get_handler(self, i, d):
        try:
            func = getattr(self, "%s_%d" % (d, i))
        except AttributeError:
            raise InvalidInterrupt("Port %d is not defined." % i)
        return func
    def input(self, i):
        func = self.get_handler(i, 'in')
        return func()
    def output(self, i, v):
        func = self.get_handler(i, 'out')
        func(v)
    def cycle(self):
        """ If this is overridden, it is called on every CPU cycle so that the device can do something. """
        pass
    def start(self):
        """ If this is overridden, it is called during the CPU boot-up sequence to initialize the actual device. """
        pass
    def stop(self):
        """ If this is overridden and does something in your own IO hook, then it is called when the CPU halts.  Great for closing files, pipes, etc... """
        pass

class HelloWorldHook(BaseCPUDevice):
    """ This is an example I/O Hook which demonstrates how the I/O hook system works. """
    ports = [32,33]
    io_address = 0x0
    def start(self):
        self.mem = 'Hello World!\x00'
    def out_32(self, addr):
        self.addr = addr
    def in_32(self):
        self.cpu.mem[self.addr] = "Hello World!"
        return self.addr
    def out_33(self, reg):
        sys.stdout.write("%s\n" % getattr(self.cpu, self.cpu.var_map[reg]).b)
    def in_33(self):
        return self.count
    def mem_read(self, addr):
        try:
            return ord(self.mem[addr])
        except IndexError:
            raise MemoryProtectionError('Unable to read from memory address.')
    def mem_write(self, addr, byte):
        raise MemoryProtectionError('Unable to write to memory address.')

class ConIOHook(BaseCPUDevice):
    """ This implements a basic tty-based display and keyboard for basic input/output operations from the CPU. """
    ports = [8000, 4000]
    def start(self):
        """ This will set-up the Linux terminal to noncanonical mode, which is needed by this module to process RAW keyboard buffer. """
        if termios:
            self.attr = termios.tcgetattr(sys.stdin)
            self.oldattr = self.attr[3]
            self.attr[3] = self.attr[3] & ~termios.ICANON
            termios.tcsetattr(sys.stdin, termios.TCSANOW, self.attr)
        else:
            sys.stderr.write('termios not loaded, simulation will be limited.\n')
    def cleanup(self):
        """ This will place the Linux terminal back into canonical mode, which enables Line-per-Line buffers. """
        if termios:
            self.attr[3] = self.oldattr
            termios.tcsetattr(sys.stdin, termios.TCSANOW, self.attr)
    def out_8000(self, reg):
        sys.stdout.write('%s' % chr(reg))
    def in_4000(self):
        if termios:
            sys.stdin.flush()
            return ord(sys.stdin.read(1))
        else:
            raise CPUException("CPU: Single key input not supported on this platform.")
