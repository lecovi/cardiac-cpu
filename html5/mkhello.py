"""
This file generates an example hello.bin which can be loaded into your browser.
This file was created to test out the virtual machine before the assembler is built.
An assembler compatible with this virtual machine will be available soon.
"""

data = chr(7)+chr(14)+'Click me!'+chr(0)
data +=chr(4)+chr(5)
data +=chr(1)+'Hello World!'+chr(0)
data +=chr(5)+chr(6)+chr(21+12)
data +=chr(3)+chr(14)
data +=chr(2)

open('hello.bin', 'wb').write(data)
