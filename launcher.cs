using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;

// A9 自动驾驶台 —— exe 启动器
// 行为由 exe 自身的文件名决定：
//   A9控制台.exe  -> 打开桌面窗口（pythonw，无控制台）
//   采集模板.exe  -> python main.py capture
//   采集车辆.exe  -> python main.py capture_car
//   采集坐标.exe  -> python main.py coords
//   环境自检.exe  -> python main.py check
class A9Launcher
{
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    static extern int MessageBoxW(IntPtr hWnd, string text, string caption, uint type);

    static void Fail(string msg)
    {
#if WINDOWLESS
        MessageBoxW(IntPtr.Zero, msg, "A9 自动驾驶台", 0x10);
#else
        Console.WriteLine(msg);
        Console.WriteLine();
        Console.WriteLine("按任意键退出...");
        Pause();
#endif
    }

    static int Main(string[] argv)
    {
        string exePath = Assembly.GetExecutingAssembly().Location;
        string dir = Path.GetDirectoryName(exePath);
        string name = Path.GetFileNameWithoutExtension(exePath);

        string runArgs;
        bool windowless;

        if (name.Contains("采集车辆")) { runArgs = "main.py capture_car"; windowless = false; }
        else if (name.Contains("采集模板")) { runArgs = "main.py capture"; windowless = false; }
        else if (name.Contains("采集坐标")) { runArgs = "main.py coords"; windowless = false; }
        else if (name.Contains("环境自检")) { runArgs = "main.py check"; windowless = false; }
        else { runArgs = "gui.py"; windowless = true; }   // 默认：桌面窗口

        if (argv.Length > 0 && argv[0] == "--which")
        {
            Console.WriteLine("exe=[" + name + "] -> " + runArgs);
            return 0;
        }

        string py = FindPython(dir);
        if (py == null)
        {
            Fail("找不到 Python 解释器。\n\n请在程序目录下的 python_path.txt 中，\n写入 python.exe 的完整路径。");
            return 1;
        }

        string program = windowless ? PythonwFor(py) : py;

#if !WINDOWLESS
        Console.WriteLine("A9 自动驾驶台");
        Console.WriteLine("Python  : " + py);
        Console.WriteLine("工作目录: " + dir);
        Console.WriteLine("执行    : " + runArgs);
        Console.WriteLine(new string('-', 52));
#endif

        ProcessStartInfo psi = new ProcessStartInfo();
        psi.FileName = program;
        psi.Arguments = runArgs;
        psi.WorkingDirectory = dir;
        psi.UseShellExecute = false;
        try
        {
            Process p = Process.Start(psi);
            p.WaitForExit();
        }
        catch (Exception e)
        {
            Fail("启动失败: " + e.Message);
            return 1;
        }

#if !WINDOWLESS
        Console.WriteLine(new string('-', 52));
        Console.WriteLine("已结束。按任意键关闭窗口...");
        Pause();
#endif
        return 0;
    }

    static void Pause()
    {
        try { Console.ReadKey(); }
        catch { }
    }

    // 找同目录的 pythonw.exe（无控制台版）
    static string PythonwFor(string py)
    {
        try
        {
            string w = Path.Combine(Path.GetDirectoryName(py), "pythonw.exe");
            if (File.Exists(w)) return w;
        }
        catch { }
        return py;
    }

    static string FindPython(string dir)
    {
        // 1) python_path.txt
        try
        {
            string cfg = Path.Combine(dir, "python_path.txt");
            if (File.Exists(cfg))
            {
                string p = File.ReadAllText(cfg).Trim();
                if (p.Length > 0 && File.Exists(p)) return p;
            }
        }
        catch { }

        // 2) PATH（跳过应用商店别名）
        string fromPath = WhichOnPath("python.exe");
        if (fromPath != null) return fromPath;

        // 3) 常见位置
        string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        string[] guesses = new string[] {
            Path.Combine(local, @"Python\pythoncore-3.14-64\python.exe"),
            Path.Combine(local, @"Python\pythoncore-3.13-64\python.exe"),
            Path.Combine(local, @"Python\pythoncore-3.12-64\python.exe"),
            Path.Combine(local, @"Programs\Python\Python314\python.exe"),
            Path.Combine(local, @"Programs\Python\Python313\python.exe"),
            Path.Combine(local, @"Programs\Python\Python312\python.exe"),
            @"C:\Python314\python.exe",
            @"C:\Python313\python.exe",
            @"C:\Python312\python.exe"
        };
        for (int i = 0; i < guesses.Length; i++)
        {
            try { if (File.Exists(guesses[i])) return guesses[i]; }
            catch { }
        }
        return null;
    }

    static string WhichOnPath(string exe)
    {
        try
        {
            string path = Environment.GetEnvironmentVariable("PATH");
            if (path == null) return null;
            string[] parts = path.Split(';');
            for (int i = 0; i < parts.Length; i++)
            {
                string d = parts[i].Trim();
                if (d.Length == 0) continue;
                if (d.ToLower().Contains("windowsapps")) continue;
                try
                {
                    string full = Path.Combine(d, exe);
                    if (File.Exists(full)) return full;
                }
                catch { }
            }
        }
        catch { }
        return null;
    }
}
