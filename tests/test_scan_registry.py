import sys, os, types, tempfile
sys.path.insert(0, 'portabilis')

HKLM, HKCU = -2147483646, -2147483649
K64, K32, READ = 0x100, 0x200, 0x20019
UN = 'SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall'
UN32 = 'SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall'

tmp = tempfile.mkdtemp()
exe64 = os.path.join(tmp, 'a.exe'); open(exe64, 'w').write('x')
exe32 = os.path.join(tmp, 'legacy.exe'); open(exe32, 'w').write('xx')

BASES = {
 ('HKLM-64', UN):   {'App64':   {'DisplayName':'App Moderno 64','DisplayVersion':'1.0','Publisher':'P1','InstallLocation':tmp,'DisplayIcon':exe64}},
 ('HKLM-32', UN):   {'Legacy32':{'DisplayName':'Programa Legado 32','DisplayVersion':'2.1','Publisher':'OldCo','InstallLocation':tmp,'DisplayIcon':exe32}},
 ('HKLM-32', UN32): {'Legacy32':{'DisplayName':'Programa Legado 32','DisplayVersion':'2.1','Publisher':'OldCo','InstallLocation':tmp,'DisplayIcon':exe32}},
 ('HKCU',   UN):   {'UserApp': {'DisplayName':'App Usuario','InstallLocation':tmp,'DisplayIcon':exe64},
                    'SysComp': {'DisplayName':'Componente Oculto','SystemComponent':'1','InstallLocation':tmp}},
}

wr = types.ModuleType('winreg')
wr.HKEY_LOCAL_MACHINE, wr.HKEY_CURRENT_USER = HKLM, HKCU
wr.KEY_READ, wr.KEY_WOW64_64KEY, wr.KEY_WOW64_32KEY = READ, K64, K32

class Key:
    def __init__(self, base, name, vals): self.base, self.name, self.vals = base, name, vals

def _base_of(hive, path, access):
    h = 'HKCU' if hive == HKCU else ('HKLM-32' if (access & K32) else 'HKLM-64')
    if path.startswith('SOFTWARE\\WOW6432Node'): h = 'HKLM-32'
    return (h, path)

def OpenKey(hive, path, *args, **kw):
    if isinstance(hive, Key):
        b = hive.base[0]
        bp = hive.base[1]
        nm = path
        apps = BASES.get((b, bp))
        if apps is None or nm not in apps: raise OSError(2, 'nf')
        return Key((b, bp), nm, apps[nm])
    access = args[1] if len(args) > 1 else (kw.get('access') or READ)
    b = _base_of(hive, path, access)
    if b in BASES:
        return Key(b, '', None)
    raise OSError(2, 'nf')

def EnumKey(key, i):
    if key.name: raise OSError(255, 'leaf')
    kids = sorted(BASES[key.base].keys())
    if i >= len(kids): raise OSError(255, 'end')
    return kids[i]

def QueryValueEx(key, name):
    if key.vals is None or name not in key.vals: raise OSError(2, 'novalue')
    return (key.vals[name], 1)

wr.OpenKey, wr.EnumKey, wr.QueryValueEx = OpenKey, EnumKey, QueryValueEx
wr.CloseKey = lambda k: None
sys.modules['winreg'] = wr

import scan
apps = scan.enumerate_registry_apps()
for a in apps: print(a.name, '|', a.version, '|', a.source, '|', a.main_exe)
names = [a.name for a in apps]
assert 'Programa Legado 32' in names, "32-bit nao encontrado!"
assert 'App Moderno 64' in names
assert 'App Usuario' in names
assert 'Componente Oculto' not in names, "SystemComponent vazou!"
a32 = next(a for a in apps if a.name == 'Programa Legado 32')
scan.analyze_app(a32)
print('estrategia legado 32:', a32.strategy)
assert scan.is_registry_source(a32.source)
print("OK: varredura tipo Painel de Controle encontra apps 32 e 64 bits")
