Simple CPU/Virtual Machine
--------------------------

This is a Virtual Machine that I have been working on for quite sometime now, it is currently
being used in my online multiplayer hacking simulation game, Hacker's Edge, but the game itself
is not yet available to be played.  This virtual machine has become more advanced than it once
was when I first released it, now supporting many more opcodes, and trying to operate more along
the line of a modern CPU.

##### Features

 - Assembler and Debugger included
 - Opcodes are similar to that of 16-bit x86 assembly
 - Fairly easy to read and understand code
 - Ability to mark labels and variables in assembler code
 - New Memory mapping system being developed
    - Will include the ability to use Memory mapped I/O
    - Support for unique memory spaces with read/write protection


##### Future plans

 - HTML5 Virtual machine to run the same bytecode in a web browser using JavaScript
    - Will be-able to make use of both Canvas and HTML forms
    - Will be-able to make use of AJAX to GET and POST data
 - Updated memory management system, currently in progress
    - This will allow for the use of memory mapped I/O
 - The ability to create apps which can either use SDL or the current OS's native window widgets
    - On Linux this will go through GTK2 or TK
    - On MS-Windows this will go through native Win32 GUI APIs or TK
    - In HTML5, this will use the Canvas and standard HTML widgets
 - Bytecode encryption, so that in order to run an app, you must enter in a passphrase
 - Add more opcodes and remove unneeded opcodes
 - Ability to easily package assets into virtual machine binary files
 - Add headers to Virtual Machine binary files
    - Headers will enable use of runtime linking support so that binaries can be loaded at any address
    - Will also enable dynamic asset loading
 - Port over to FreePascal to provide fast code execution and easy distribution
    - With FreePascal, only a single EXE/ELF and your VM binaries would be needed to run
