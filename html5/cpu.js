var app;

function stdout(data){ document.getElementById('app').innerHTML += data; }

function chr(int){ return String.fromCharCode(int); }
function ord(ch){ return ch.charCodeAt(0); }

function appError(msg){
  alert('The application had an internal process error.');
  throw new Error(msg);
}

function MemoryMap(){
  mem = new Uint8Array(0x2000);
  read = true;
  write = true;
  this.clear = function(){
    for (var i=0;i<mem.length;i++){ mem[i] = chr(0); }
  }
  this.mem_read = function(addr){
    if (!read){ appError('Attempted to read from protected memory space: '+addr); }
    byte = mem[addr];
    if (byte == undefined)
      return chr(0);
    return byte;
  }
  this.mem_write = function(addr, byte){
    if (!write){ appError('Attempted to write to protected memory space: '+addr); }
    if (isNaN(byte)){ mem[addr] = ord(byte); }else{ mem[addr] = byte; }
  }
  this.write_protect = function(){ write = false; }
  this.read_protect = function(){ read = false; }
  this.clear();
}

function MemoryController(){
  map0 = new MemoryMap();
  mapA = new MemoryMap();
  this.mem_read = function(addr){
    var ha = (addr>>12)&0xe;
    switch(ha){
      case 0x0:
        return map0.mem_read(addr&0x1fff);
        break;
      case 0xa:
        return mapA.mem_read(addr&0x1fff);
        break;
      default:
        appError('Memory out of range: '+addr);
        break;
    }
  }
  this.mem_write = function(addr, byte){
    var ha = (addr>>12)&0xe;
    switch(ha){
      case 0x0:
        map0.mem_write(addr&0x1fff, byte);
        break;
      case 0xa:
        mapA.mem_write(addr&0x1fff, byte);
        break;
      default:
        appError('Memory out of range: '+addr);
        break;
    }
  }
  this.mem_read16 = function(addr){
    return this.mem_read(addr)|this.mem_read(addr+1)<<8;
  }
  this.mem_write16 = function(addr, word){
    this.mem_write(addr, word&0xff);
    this.mem_write(addr+1, word>>8);
  }
  this.get_byte = function(addr){
    var b = ord(this.mem_read(addr));
    var flags = [b & (1 << 5),b & (1 << 6),b & (1 << 7)];
    b &= ~(1 << 5);
    b &= ~(1 << 6);
    b &= ~(1 << 7);
    return [b, flags];
  }
  this.get_char = function(addr){
    var byte = this.get_byte(addr);
    if (byte[0] > 0 && byte[0] < 27)
      return [chr(byte[0]+64), byte[1]];
    return byte;
  }
  this.get_string = function(addr){
    var result = '';
    while(true){
      byte = this.get_char(addr); addr++;
      ch = byte[0];
      if (byte[1][2]>0)
        ch = ch.toLowerCase();
      result += ch;
      if (byte[1][0]>0)
        break;
    }
    return [result, addr];
  }
  this.lockMap0 = function(){
    map0.write_protect();
  }
}

function CPU(binURL){
  var pc, ir, acc, running;
  var mem = new MemoryController();
  function loadbin(binURL){
    var bf = new BinFileReader(binURL);
    for (var i=0;i<bf.getFileSize();i++){ mem.mem_write(i, bf.readNumber(1)); }
  }
  function fetch(){ ++pc; return mem.mem_read(pc-1); }
  function read_string(){
    var result = '';
    var ch = 1;
    while(ch!=0){ ch=fetch(); result+=chr(ch); }
    return result;
  }
  function process(){
    var op = fetch();
    switch(op){
      case 1:
        stdout(read_string()+'<br/>');
        break;
      case 2:
        running = false;
        break;
      case 3:
        jmp = fetch();
        pc = jmp;
        break;
      case 4:
        acc = fetch();
        break;
      case 5:
        --acc;
        break;
      case 6:
        jmp = fetch();
        if (acc < 1)
          pc = jmp;
        break;
      case 7:
        stdout('<button onclick="app.run('+fetch()+');">'+read_string()+'</button><br/>');
        break;
      default:
        appError('Invalid OpCode: '+op+'\nPC: '+pc);
        break;
    }
  }
  this.run = function(addr){
    running = true;
    pc = addr;
    while(running)
      process();
  }
  loadbin(binURL);
  mem.lockMap0();
  this.run(0);
}

function appInit(binURL){
  app = new CPU(binURL);
}
