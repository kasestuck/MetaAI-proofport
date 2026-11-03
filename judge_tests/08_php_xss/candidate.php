<?php
namespace JudgeXss;
function render($value) { echo htmlspecialchars($value, ENT_QUOTES, 'UTF-8'); return strlen($value); }
