using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Windows.Forms;
[assembly: AssemblyTitle("PhoneWorkbench8070")]
[assembly: AssemblyProduct("Phone Workbench 8070")]
[assembly: AssemblyVersion("@@VERSION@@.0")]
[assembly: AssemblyFileVersion("@@VERSION@@.0")]
internal static class Launcher {
    private static string Quote(string value) {
        if (value.Contains("\"") || value.Contains("\n") || value.Contains("\r")) throw new ArgumentException("Invalid path");
        return "\"" + value + "\"";
    }
    [STAThread] private static int Main(string[] args) {
        bool check = args.Length == 2 && args[0] == "--check-install";
        try {
            string root = AppDomain.CurrentDomain.BaseDirectory;
            string runtime = Path.Combine(root, "runtime");
            string file, arguments;
            if (check) {
                file = Path.Combine(runtime, "python.exe");
                arguments = Quote(Path.Combine(root,"tools","check_8070_install.py")) + " --output " + Quote(Path.GetFullPath(args[1]));
            } else if (args.Length == 1 && args[0] == "--backend-control") {
                file = Path.Combine(runtime,"pythonw.exe");
                arguments = Quote(Path.Combine(root,"BackendControl.pyw"));
            } else if (args.Length == 0) {
                file = Path.Combine(root,"client","PhoneWorkbench8070Client.exe");
                arguments = "";
            } else return 2;
            if (!File.Exists(file)) throw new FileNotFoundException("安装文件缺失，请重新安装。",file);
            ProcessStartInfo info = new ProcessStartInfo(file,arguments);
            info.WorkingDirectory=root; info.UseShellExecute=false; info.CreateNoWindow=true;
            info.WindowStyle=ProcessWindowStyle.Hidden;
            info.EnvironmentVariables["PATH"]=runtime+Path.PathSeparator+Environment.GetEnvironmentVariable("PATH");
            info.EnvironmentVariables["PYTHONUTF8"]="1";
            info.EnvironmentVariables["PYTHONIOENCODING"]="utf-8";
            info.EnvironmentVariables.Remove("PYTHONHOME"); info.EnvironmentVariables.Remove("PYTHONPATH");
            using(Process process=Process.Start(info)) {
                if(check) { process.WaitForExit(); return process.ExitCode; }
            }
            return 0;
        } catch(Exception error) {
            if(!check) MessageBox.Show(error.Message,"手机工作台 8070",MessageBoxButtons.OK,MessageBoxIcon.Error);
            return 1;
        }
    }
}
