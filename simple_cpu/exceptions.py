
class CPUException(Exception):
    """ This exception is raised if there is a bytecode runtime error, usually caused by an error in the user's bytecode. """
    pass

class InvalidInterrupt(CPUException):
    """ This exception is raised if the user's code trying to access an I/O port on the CPU which has yet to be written/configured. """
    pass

class MemoryProtectionError(CPUException):
    """ This exception is raised if the user's code attempts to read or write from protected memory it cannot access. """
    pass
