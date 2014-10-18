CPU Simulator for generating dynamic web pages
----------------------------------------------

This is a version of the CPU simulator which will have similar functionality to the
command-line version once it is complete.  The idea is that you will be-able to
dynamically drive a web application using it's virtual machine.  This is a very
early release of this tool and shouldn't be used yet.  You can try it and play
around with it, if you would like.  There is no compatible assembler yet, but that
will be available shortly, and will use the existing assembler to build binaries.

##### Currently available features

These are features which I was testing out, the API will not remain, this API was
just used to test out the actual VM within the browser to prep the code.

 - Write string data into a DIV labaled "app".
 - Loops and a basic conditional jump based on the accumulator.
 - Creating a clickable HTML button which calls VM code directly.

The idea behind the click-able button mentioned here is to enable the VM to be
triggered by end-user actions and requests.  So, you could perform some task
when the button is clicked, such as fetching data from the server, or posting
data to the server, or collecting data into the built-in memory manager.

One of the newest features for CPU simulator is the "Memory mapper" system,
which will work similar to some embedded systems and older computer hardware
like the Apple ][, C64, and 80s/90s video game consoles.  These maps will also
support "Memory mapped I/O", and this will replace the current "IN/OUT" opcodes
entirely in favor of this.  Memory mapped I/O will also enable direct access to
the current devices "framebuffer", this can be used to render graphics among other
things.  On the Deskop, this will go through the SDL libraries, and mapping images
into the SDL Surface will be done by direct manipulation of the memory map.  In the
browser version of the simulator, this will go through the HTML5 Canvas, so this
will enable one to develop applications easily for both the Deskop and the Web using
a specialized virtual machine.  At least these are my upcoming plans for this.

Both the Desktop and Web will also support forms and regular content, and this will
also be transparent regardless of where the virtual machine app is being run.  So, again
this can enable the easy develop of cross-platform apps, but just writing and compiling
the app only once.  Furthermore, no additional plugins will ever be needed in the case of
the browser, and applications "will just run", in contrast to past similar systems like
Java.  I am hoping that once I can finalize the bytecodes for the virtual machine, that
perhaps I can begin work on a higher level compiler to make development much easier.

It is also possible for third party applications to generate bytecode as well, say
a popular game engine enables an option to export a game to this particular bytecode,
then it will enable that game to run on all popular platforms, including mobile devices.
