import lldb
import os
import time
import _thread

if __name__ == "__main__":
    print("Run as LLDB script!")
    exit()

COLORS = { "BLACK": "\033[30m", "RED": "\033[31m", "GREEN": "\033[32m", "YELLOW": "\033[33m", "BLUE": "\033[34m", "MAGENTA": "\033[35m", "CYAN": "\033[36m", "WHITE": "\033[37m", "RESET": "\033[0m", "BOLD": "\033[1m", "UNDERLINE": "\033[4m" }

old_register_values = None

def get_frame():
    ret = None
    for thread in lldb.debugger.GetSelectedTarget().process:
        if thread.GetStopReason() != lldb.eStopReasonNone and thread.GetStopReason() != lldb.eStopReasonInvalid:
            ret = thread.GetFrameAtIndex(0)
            break
    if ret is None:
        print("[-] warning: get_frame() failed. Is the target binary started?")

    return ret

# Continuously dereferences memory and prints possible pointer chains
def dereference_memory(mem_addr, str, depth=0):
    if depth == 8:
        return True, ""

    # Print the symbol name
    symbol_name = lldb.SBAddress(mem_addr, lldb.debugger.GetSelectedTarget()).GetSymbol().GetName()
    if symbol_name is not None:
        str +=  COLORS["GREEN"] +  " (@ " + symbol_name + ")" + COLORS["RESET"]

    error = lldb.SBError()
    mem = lldb.debugger.GetSelectedTarget().GetProcess().ReadMemory(mem_addr, 8, error)

    if error.Success() == True:
        value = int.from_bytes(mem, "little")

        str += " -> " + hex(value)

        is_end, m = dereference_memory(value, str, depth + 1)
        if is_end:
            # Check if the memory is a string
            try:
                s = lldb.debugger.GetSelectedTarget().GetProcess().ReadCStringFromMemory(mem_addr, 64, error)
                if error.Success() == True:
                    if len(s) > 0:
                        str += " | " +  s
            except:
                return True, str
        else:
            str += m
    else:
        return True, ""

    return False, str

def print_registers():
    global COLORS
    global old_register_values

    registers = {}

    print(chr(27) + "[2J")

    str = COLORS["RESET"] + "-----------------------------------------------------------------------------------------------------------------------[regs]\n"

    frame = get_frame()
    if frame is None:
        return None

    for reg_kind in frame.GetRegisters():
        if "General Purpose".lower() in reg_kind.GetName().lower():
            for reg in reg_kind:
                reg_name = reg.GetName()

                # Skip 32-bit ARM registers
                if reg_name[0] != "w":
                    registers[reg_name] = reg.unsigned

    for register_name, register_value in registers.items():
        modified = True

        mem_chain = dereference_memory(register_value, "")[1]

        if old_register_values is not None:
            if old_register_values[register_name] == register_value:
                modified = False

        if len(register_name) == 2:
            register_name += "  "
        if len(register_name) == 3:
            register_name += " "

        if modified:
            color = COLORS["RED"]
        else:
            color = COLORS["RESET"]

        str += COLORS["GREEN"] + register_name + ": " + color + hex(register_value) + mem_chain + "\n"

    old_register_values = registers

    return str, registers

def print_stack_trace(sp):
    global COLORS

    str = COLORS["RESET"] + "-----------------------------------------------------------------------------------------------------------------------[stack]\n"

    for i in range(0, 8):
        s = sp + i * 8
        str += COLORS["GREEN"] + hex(s) + ": " + COLORS["RED"] + dereference_memory(s, "")[1][4:] + "\n"

    return str

def __lldb_init_module(debugger, internal_dict):
    print("Init llef...")

    res = lldb.SBCommandReturnObject()
    ci = debugger.GetCommandInterpreter()

    # Preferring Intel syntax over AT&T syntax
    ci.HandleCommand("settings set target.x86-disassembly-flavor intel", res)

    # Register the stop handler
    ci.HandleCommand("command script add -f llef.HandleHookStopOnTarget HandleHookStopOnTarget", res)
    ci.HandleCommand("command script add -f llef.HandleHookStopOnTarget ctx", res)
    ci.HandleCommand("command script add -f llef.HandleHookStopOnTarget context", res)
    ci.HandleCommand("target stop-hook add -o \"HandleHookStopOnTarget\"", res)

    # Breakpoint on main()
    ci.HandleCommand("b main", res)

def HandleHookStopOnTarget(debugger, command, result, dict):
    if os.getenv("PATH").startswith("/Applications/Xcode.app"):
        return

    debugger.SetAsync(True)

    str = ""

    reg_str, registers = print_registers()
    str += reg_str

    str += print_stack_trace(registers["sp"])

    str += COLORS["RESET"] + "-----------------------------------------------------------------------------------------------------------------------\n"

    result.PutCString(str)
    result.SetStatus(lldb.eReturnStatusSuccessFinishResult)
    return 0