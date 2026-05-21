// Leng Xiaobei Trae IDE Plugin
// Integrates Leng Xiaobei's autonomous programming and architecture optimization capabilities

const vscode = require('vscode');
const { exec } = require('child_process');
const path = require('path');

/**
 * Activates the extension
 * @param {vscode.ExtensionContext} context
 */
function activate(context) {
    console.log('Leng Xiaobei extension activated');

    // Register commands
    let analyzeCode = vscode.commands.registerCommand('lengxiaobei.analyzeCode', async () => {
        await analyzeCodeCommand();
    });

    let generateCode = vscode.commands.registerCommand('lengxiaobei.generateCode', async () => {
        await generateCodeCommand();
    });

    let optimizeArchitecture = vscode.commands.registerCommand('lengxiaobei.optimizeArchitecture', async () => {
        await optimizeArchitectureCommand();
    });

    let runEvolution = vscode.commands.registerCommand('lengxiaobei.runEvolution', async () => {
        await runEvolutionCommand();
    });

    // Push to context
    context.subscriptions.push(analyzeCode);
    context.subscriptions.push(generateCode);
    context.subscriptions.push(optimizeArchitecture);
    context.subscriptions.push(runEvolution);
}

/**
 * Analyzes code using Leng Xiaobei
 */
async function analyzeCodeCommand() {
    try {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            vscode.window.showErrorMessage('No active editor found');
            return;
        }

        const filePath = editor.document.uri.fsPath;
        const result = await runLengXiaobeiCommand('analyze', { file: filePath });
        vscode.window.showInformationMessage('Code analysis completed: ' + result.message);
    } catch (error) {
        vscode.window.showErrorMessage('Error analyzing code: ' + error.message);
    }
}

/**
 * Generates code using Leng Xiaobei
 */
async function generateCodeCommand() {
    try {
        const prompt = await vscode.window.showInputBox({
            prompt: 'Enter code generation prompt',
            placeHolder: 'e.g., Create a function that calculates Fibonacci numbers'
        });

        if (!prompt) return;

        const result = await runLengXiaobeiCommand('generate', { prompt: prompt });
        
        // Create a new file with the generated code
        const document = await vscode.workspace.openTextDocument({
            content: result.code,
            language: 'python'
        });
        await vscode.window.showTextDocument(document);
        
        vscode.window.showInformationMessage('Code generated successfully');
    } catch (error) {
        vscode.window.showErrorMessage('Error generating code: ' + error.message);
    }
}

/**
 * Optimizes architecture using Leng Xiaobei
 */
async function optimizeArchitectureCommand() {
    try {
        const workspaceFolder = vscode.workspace.workspaceFolders[0];
        if (!workspaceFolder) {
            vscode.window.showErrorMessage('No workspace folder found');
            return;
        }

        const projectPath = workspaceFolder.uri.fsPath;
        const result = await runLengXiaobeiCommand('optimize', { project: projectPath });
        
        // Show optimization results
        vscode.window.showInformationMessage('Architecture optimization completed: ' + result.message);
        
        // If there are specific recommendations, show them
        if (result.recommendations) {
            vscode.window.showInformationMessage('Optimization recommendations: ' + result.recommendations.join(', '));
        }
    } catch (error) {
        vscode.window.showErrorMessage('Error optimizing architecture: ' + error.message);
    }
}

/**
 * Runs evolution process using Leng Xiaobei
 */
async function runEvolutionCommand() {
    try {
        const workspaceFolder = vscode.workspace.workspaceFolders[0];
        if (!workspaceFolder) {
            vscode.window.showErrorMessage('No workspace folder found');
            return;
        }

        const projectPath = workspaceFolder.uri.fsPath;
        
        // Show progress
        await vscode.window.withProgress({
            location: vscode.ProgressLocation.Window,
            title: 'Leng Xiaobei Evolution',
            cancellable: true
        }, async (progress, token) => {
            progress.report({ message: 'Running evolution process...' });
            
            const result = await runLengXiaobeiCommand('evolve', { project: projectPath });
            progress.report({ message: 'Evolution completed' });
            
            vscode.window.showInformationMessage('Evolution process completed: ' + result.message);
            
            if (result.changes) {
                vscode.window.showInformationMessage('Changes made: ' + result.changes.length + ' files modified');
            }
        });
    } catch (error) {
        vscode.window.showErrorMessage('Error running evolution: ' + error.message);
    }
}

/**
 * Runs a Leng Xiaobei command
 * @param {string} command - The command to run
 * @param {object} params - The parameters for the command
 * @returns {Promise<object>} - The result of the command
 */
async function runLengXiaobeiCommand(command, params) {
    return new Promise((resolve, reject) => {
        const pythonScript = path.join(__dirname, '../../src/evolution_engine.py');
        const args = [
            pythonScript,
            command,
            JSON.stringify(params)
        ];

        exec(`python3 ${args.join(' ')}`, (error, stdout, stderr) => {
            if (error) {
                reject(new Error(`Command failed: ${stderr}`));
                return;
            }

            try {
                const result = JSON.parse(stdout);
                resolve(result);
            } catch (parseError) {
                reject(new Error(`Failed to parse response: ${stdout}`));
            }
        });
    });
}

/**
 * Deactivates the extension
 */
function deactivate() {
    console.log('Leng Xiaobei extension deactivated');
}

module.exports = {
    activate,
    deactivate
};
