#!/usr/bin/fish
for tickscript in $argv
  set taskname (basename $tickscript .tick)
  echo "defining ang reloading $taskname with $tickscript"
  kapacitor define $taskname -tick $tickscript
  kapacitor reload $taskname
end
