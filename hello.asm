mov ds,cs
jmp *main
label hello
data "Hello Simple CPU Simulator!"
label main
mov ax,*hello
int 10
mov ax,10
out 8000,ax
hlt
