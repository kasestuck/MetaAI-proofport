<?php
/* Original trusted harness, compatible with PHP 7.4 and 8.3. Docker ONLY.
 * Never supplied expected golden outputs. No Composer/network installation.
 */
namespace ProofportHarness;

final class UnsupportedValue extends \RuntimeException {}

function normalized($value, $depth = 0) {
    if ($depth > 16) throw new UnsupportedValue('Result nesting limit');
    if ($value === null) return array('type' => 'null');
    if (is_bool($value)) return array('type' => 'bool', 'value' => $value);
    if (is_int($value)) return array('type' => 'int', 'value' => (string)$value);
    if (is_float($value)) return array('type' => 'float', 'value' => bin2hex(pack('E', $value)));
    if (is_string($value)) return array('type' => 'bytes', 'base64' => base64_encode($value));
    if (is_array($value)) {
        if (count($value) > 256) throw new UnsupportedValue('Result size limit');
        $items = array();
        foreach ($value as $key => $item) $items[] = array('key' => normalized($key, $depth + 1), 'value' => normalized($item, $depth + 1));
        return array('type' => 'array', 'items' => $items);
    }
    throw new UnsupportedValue('Objects/resources are outside the verified codec');
}

function project_file($relative) {
    if (!is_string($relative) || strpos($relative, '\\') !== false || strpos($relative, ':') !== false || strpos($relative, "\0") !== false) throw new \RuntimeException('Invalid file');
    foreach (explode('/', $relative) as $part) if ($part === '' || $part === '.' || $part === '..' || $part[0] === '.') throw new \RuntimeException('Invalid file');
    $path = realpath('/src/' . $relative);
    if ($path === false || strpos($path, '/src/') !== 0 || !is_file($path) || substr($path, -4) !== '.php') throw new \RuntimeException('Missing project PHP file');
    return $path;
}

function include_project($path) { return require_once $path; }

function record_case($case) {
    $warnings = array(); $deprecations = array();
    set_error_handler(function($level, $message) use (&$warnings, &$deprecations) {
        $item = array('level' => $level, 'message' => normalized($message));
        if ($level === E_DEPRECATED || $level === E_USER_DEPRECATED) $deprecations[] = $item;
        else $warnings[] = $item;
        return true;
    });
    ob_start();
    $result = array('id' => $case['id']);
    try {
        $file = project_file($case['file']);
        include_project($file);
        if (!is_string($case['call']) || !preg_match('/^[a-zA-Z_][a-zA-Z_0-9]*(?:\\\\[a-zA-Z_][a-zA-Z_0-9]*)*$/D', $case['call'])) throw new \RuntimeException('Invalid function');
        if (!function_exists($case['call'])) { $result['status'] = 'harness_error'; }
        else {
            $reflection = new \ReflectionFunction($case['call']);
            if ($reflection->isInternal() || realpath($reflection->getFileName()) !== $file) { $result['status'] = 'harness_error'; }
            else { $value = call_user_func_array($case['call'], $case['args']); $result['value'] = normalized($value); $result['status'] = 'return'; }
        }
    } catch (UnsupportedValue $error) {
        $result['status'] = 'unsupported_result';
    } catch (\Throwable $error) {
        $result['status'] = $error instanceof \Error ? 'runtime_error' : 'exception';
        $result['error'] = array('class' => get_class($error), 'message' => normalized($error->getMessage()), 'code' => normalized($error->getCode()));
    } finally {
        $result['stdout'] = base64_encode(ob_get_clean());
        restore_error_handler();
    }
    $result['warnings'] = $warnings; $result['deprecations'] = $deprecations;
    return $result;
}

function child_process($command) {
    $out = '/tmp/proofport-out'; $err = '/tmp/proofport-err';
    $process = proc_open($command, array(0 => array('file', '/dev/null', 'r'), 1 => array('file', $out, 'w'), 2 => array('file', $err, 'w')), $pipes, '/tmp');
    if (!is_resource($process)) throw new \RuntimeException('Cannot start trusted child command');
    $exit = proc_close($process);
    clearstatcache(true, $out); clearstatcache(true, $err);
    if (filesize($out) > 131072 || filesize($err) > 131072) throw new \RuntimeException('Child output limit');
    return array('exit_code' => $exit); // Raw source/errors may contain secrets: not exported.
}

function main($input) {
    $result = array('protocol' => 'proofport-php-1', 'php' => PHP_VERSION, 'action' => $input['action']);
    if ($input['action'] === 'version') return $result;
    if ($input['action'] === 'lint') {
        $files = array();
        foreach ($input['files'] as $relative) {
            $path = project_file($relative);
            // Validated /src/... absolute path cannot be a CLI option. PHP 8.3
            // treats -- after -l as stdin selection rather than the lint file.
            $check = child_process(array(PHP_BINARY, '-n', '-d', 'auto_prepend_file=', '-d', 'auto_append_file=', '-l', $path));
            $files[] = array('file' => $relative, 'exit_code' => $check['exit_code'], 'passed' => $check['exit_code'] === 0);
        }
        $result['files'] = $files;
    } elseif ($input['action'] === 'cases') {
        $result['cases'] = array();
        foreach ($input['cases'] as $case) $result['cases'][] = record_case($case);
    } elseif ($input['action'] === 'tests') {
        // An explicit local convention, not automatic PHPUnit discovery.
        ob_start();
        $tests = include_project(project_file('tests/proofport.php'));
        ob_end_clean();
        if (!is_array($tests) || count($tests) < 1 || count($tests) > 128) throw new \RuntimeException('Nonempty supported test suite required');
        $result['outcomes'] = array();
        foreach ($tests as $name => $test) {
            if (!is_string($name) || !is_callable($test)) throw new \RuntimeException('Invalid native test');
            ob_start(); $passed = true;
            try { $test(); } catch (\Throwable $error) { $passed = false; }
            ob_end_clean();
            $result['outcomes'][] = array('id' => $name, 'status' => $passed ? 'passed' : 'failed');
        }
        $result['tests_run'] = count($result['outcomes']);
    } elseif ($input['action'] === 'phpunit') {
        $config = project_file_config($input['configuration']);
        $bin = '/src/vendor/phpunit/phpunit/phpunit';
        if (!is_file($bin) || !is_file('/src/vendor/autoload.php')) throw new \RuntimeException('Local PHPUnit dependencies unavailable');
        $check = child_process(array(PHP_BINARY, '-n', $bin, '--configuration', $config, '--do-not-cache-result', '--log-junit', '/tmp/proofport-junit.xml'));
        if (!is_file('/tmp/proofport-junit.xml') || filesize('/tmp/proofport-junit.xml') > 524288) throw new \RuntimeException('Missing/oversized PHPUnit results');
        $result['exit_code'] = $check['exit_code']; $result['junit'] = base64_encode(file_get_contents('/tmp/proofport-junit.xml'));
    } else throw new \RuntimeException('Unknown action');
    return $result;
}

function project_file_config($name) {
    if (!in_array($name, array('phpunit.xml', 'phpunit.xml.dist', 'phpunit.dist.xml'), true)) throw new \RuntimeException('Unsupported PHPUnit configuration');
    return '/src/' . $name;
}

try {
    error_reporting(E_ALL);
    ini_set('display_errors', '0');
    set_error_handler(function($level, $message) { if ($level !== E_DEPRECATED && $level !== E_USER_DEPRECATED) throw new \ErrorException('PHP harness/project warning', 0, $level); return true; });
    $input = json_decode(file_get_contents('php://stdin'), true, 32, JSON_THROW_ON_ERROR);
    $result = main($input);
    echo json_encode($result, JSON_THROW_ON_ERROR);
} catch (\Throwable $error) {
    while (ob_get_level()) ob_end_clean();
    echo json_encode(array('protocol' => 'proofport-php-1', 'php' => PHP_VERSION, 'error' => 'harness_unavailable'));
    exit(2);
}
