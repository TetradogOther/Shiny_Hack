#!/usr/bin/env python3
    
import os
import subprocess
import sys
import shutil
import binascii
import textwrap
import sys
import argparse

if sys.version_info < (3, 4):
        print('Python 3.4 or later is required.')
        sys.exit(1)

# Parse arguments
parser = argparse.ArgumentParser()
parser.add_argument('--offset', metavar='offset', type=int, 
                    help='offset to insert at', default=0xf00000)
parser.add_argument('--input', metavar='file', 
                    help='input filename', default='test.gba')
parser.add_argument('--debug', action='store_true',
                    help='print symbol table')

args = parser.parse_args()

PathVar = os.environ.get('Path')
Paths = PathVar.split(';')
PATH = ""
for candidatePath in Paths:
    if "devkitARM" in candidatePath:
        PATH = candidatePath
        break
if PATH == "":
	PATH = 'C://devkitPro//devkitARM//bin'
	if os.path.isdir(PATH) == False:
		print('Devkit not found.')
		sys.exit(1)

PREFIX = 'arm-none-eabi-'
OBJCOPY = os.path.join(PATH, PREFIX + 'objcopy')
OBJDUMP = os.path.join(PATH, PREFIX + 'objdump')
NM = os.path.join(PATH, PREFIX + 'nm')
AS = os.path.join(PATH, PREFIX + 'as')
CC = os.path.join(PATH, PREFIX + 'gcc')
CXX = os.path.join(PATH, PREFIX + 'g++')

def get_text_section():
        # Dump sections
        out = subprocess.check_output([OBJDUMP, '-t', 'build/linked.o'])
        lines = out.decode().split('\n')
        
        # Find text section
        text = filter(lambda x: x.strip().endswith('.text'), lines)
        section = (list(text))[0]
        
        # Get the offset
        offset = int(section.split(' ')[0], 16)
        
        return offset
        
def symbols(subtract=0):
        out = subprocess.check_output([NM, 'build/linked.o'])
        lines = out.decode().split('\n')
        
        name = ''
        
        ret = {}
        for line in lines:
                parts = line.strip().split()
                
                if (len(parts) < 3):
                        continue
                        
                if (parts[1].lower() not in {'t','d'}):
                        continue
                        
                offset = int(parts[0], 16)
                ret[parts[2]] = offset - subtract
                
        return ret
        
def insert(rom):
        where = args.offset
        rom.seek(where)
        with open('build/output.bin', 'rb') as binary:
                data = binary.read()
        rom.write(data)
        return where
                       
def hook(rom, space, hook_at, register=0):
        # Align 2
        if hook_at & 1:
            hook_at -= 1
            
        rom.seek(hook_at)
        
        register &= 7
        
        if hook_at % 4:
            data = bytes([0x01, 0x48 | register, 0x00 | (register << 3), 0x47, 0x0, 0x0])
        else:
            data = bytes([0x00, 0x48 | register, 0x00 | (register << 3), 0x47])
            
        space += 0x08000001
        data += (space.to_bytes(4, 'little'))
        rom.write(bytes(data))

def funcwrap(rom, space, hook_at, nparams, isreturning):
        # Align 2
        if hook_at & 1:
                hook_at -= 1
            
        rom.seek(hook_at)
        nparams=nparams-1

        if nparams<4:
                data = bytes([0x10, 0xB5, 0x3, 0x4C, 0x0, 0xF0, 0x3, 0xF8, 0x10, 0xBC , (isreturning+1), 0xBC , (isreturning<<3), 0x47, 0x20, 0x47])
        else:
                k=nparams-3
                data = bytes([0x10, 0xB5, 0x82, 0xB0])
                for i in range(k+2):
                        data += bytes([ i+2, 0x9C , i, 0x94])
                data += bytes([0x0, 0x9C , (nparams-1), 0x94, 0x1, 0x9C , nparams, 0x94, 0x2, 0xB0 , (k+8), 0x4C,
                               0x0, 0xF0 , ((k<<1)+13), 0xF8, 0x82, 0xB0 , nparams, 0x9C, 0x1, 0x94 , (nparams-1), 0x9C , 0x0, 0x94])
                for i in reversed(range(k+2)):
                        data += bytes([ i, 0x9C , i+2, 0x94])
                data += bytes([0x2, 0xB0 , 0x10, 0xBC, (isreturning+1), 0xBC , (isreturning<<3), 0x47, 0x20, 0x47])
        
        space += 0x08000001
        data += (space.to_bytes(4, 'little'))
        rom.write(bytes(data))

def repoint(rom, space, repoint_at, slidefactor=0):
        rom.seek(repoint_at)
        
        space += (0x08000000+slidefactor)
        data = (space.to_bytes(4, 'little'))
        rom.write(bytes(data))

def bytereplace(rom, offset, data):

        ar=offset
        words=data.split()
        for i in range(0,len(words)):
                rom.seek(ar)
                intbyte=int(words[i],16)
                rom.write(bytes(intbyte.to_bytes(1, 'big')))
                ar += 1

with open(args.input, 'rb+') as rom:
        offset = get_text_section()
        table = symbols(offset)
        where = insert(rom)
        
        # Adjust symbol table
        for entry in table:
                table[entry] += where
        
        # Read hooks from a file
        with open('hooks', 'r') as hooklist:
                for line in hooklist:
                        if line.strip().startswith('#'): continue
                        
                        symbol, address, register = line.split()
                        offset = int(address, 16) - 0x08000000
                        try:
                                code = table[symbol]
                        except KeyError:
                                print('Symbol missing:', symbol)
                                continue

                        hook(rom, code, offset, int(register))

        # Read repoints from a file 
        with open('repoints', 'r') as repointlist:
                for line in repointlist:
                        if line.strip().startswith('#'): continue
                        if len(line.split()) is 2:
                                symbol, address = line.split()
                                offset = int(address, 16) - 0x08000000
                                try:
                                        code = table[symbol]
                                except KeyError:
                                        print('Symbol missing:', symbol)
                                        continue

                                repoint(rom, code, offset)
                        if len(line.split()) is 3:
                                symbol, address, slide = line.split()
                                offset = int(address, 16) - 0x08000000
                                try:
                                        code = table[symbol]
                                except KeyError:
                                        print('Symbol missing:', symbol)
                                        continue
                                repoint(rom, code, offset, int(slide))                        

        # Read routine repoints from a file 
        with open('routinepointers', 'r') as pointerlist:
                for line in pointerlist:
                        if line.strip().startswith('#'): continue
                        
                        symbol, address = line.split()
                        offset = int(address, 16) - 0x08000000
                        try:
                                code = table[symbol]
                        except KeyError:
                                print('Symbol missing:', symbol)
                                continue

                        repoint(rom, code, offset, 1)

        # Read routine rewrite wrapper from a file
        with open('functionrewrites', 'r') as frwlist:
                for line in frwlist:
                        if line.strip().startswith('#'): continue
                        
                        symbol, address, nparam, isreturning = line.split()
                        offset = int(address, 16) - 0x08000000
                        try:
                                code = table[symbol]
                        except KeyError:
                                print('Symbol missing:', symbol)
                                continue

                        funcwrap(rom, code, offset, int(nparam), int(isreturning))

        # Insert byte changes
        with open('bytereplacement', 'r') as replacelist:
                for line in replacelist:
                        if line.strip().startswith('#'): continue
                        offset = int(line[:8],16) - 0x08000000
                        bytereplace(rom, offset, line[9:])
                        
        if args.debug:
                width = max(map(len, table.keys())) + 1
                for key in sorted(table.keys()):
                        fstr = ('{:' + str(width) + '} {:08X}')
                        print(fstr.format(key + ':', table[key] + 0x08000000))

