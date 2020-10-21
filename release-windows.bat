
py.exe build-windows.py --sh c:\dev\cygwin64\bin\sh.exe --python cpython-3.8 --profile shared-pgo
py.exe build-windows.py --sh c:\dev\cygwin64\bin\sh.exe --python cpython-3.9 --profile shared-pgo

py.exe build-windows.py --sh c:\dev\cygwin64\bin\sh.exe --python cpython-3.8 --profile static-noopt
py.exe build-windows.py --sh c:\dev\cygwin64\bin\sh.exe --python cpython-3.9 --profile static-noopt
