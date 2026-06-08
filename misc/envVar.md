In PyCharm, there isn't a single "standard" environment variable automatically set in every shell that points to your
project root. However, PyCharm provides several ways to access or define this directory depending on your needs:

### 1. In Run/Debug Configurations (The most common way)

If you want to use an environment variable in your script, you can define one in your Run Configuration:

1. Go to **Run** > **Edit Configurations...**
2. Select your script.
3. In the **Environment variables** field, click the folder icon.
4. Add a new variable (e.g., `PROJECT_ROOT`) and use the macro `$ProjectFileDir$` as the value. PyCharm will resolve
   this to your project's main directory when you run the script.

### 2. Using the "Working Directory"

By default, PyCharm sets the **Working directory** of any Run Configuration to your project root. In Python, you can
access this path without setting any extra variables using:

```python
import os

project_root = os.getcwd()
```

*Note: This only works if you haven't changed the working directory in your configuration settings.*

### 3. Dynamic Path Discovery (Recommended for Portability)

If you want your code to find the project root regardless of how it's launched (and without relying on PyCharm-specific
settings), you can calculate it relative to your script's location.

For a script located in `python/utils/askey-files.py`:

```python
import os

# Path to the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))
# Move up two levels to reach the project root (Genealogy/)
project_root = os.path.abspath(os.path.join(script_dir, '../..', '..'))
```

### 4. Terminal Settings

If you want the variable available in the **PyCharm Terminal**:

1. Go to **Settings** (Ctrl+Alt+S).
2. Navigate to **Tools** > **Terminal**.
3. In **Environment variables**, add: `PROJECT_DIR=$ProjectFileDir$` (on Windows, you might need to use the absolute
   path or check if your shell supports the macro).

### Summary of Macros

If you are editing PyCharm settings (like Path Mappings or External Tools), you can use these built-in macros:

* `$ProjectFileDir$`: The full path to the project directory.
* `$ContentRoot$`: The path to the specific content root (usually the same as the project directory).