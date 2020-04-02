(ql:quickload "usocket")

(defpackage :socket-inspector
  (:use :common-lisp :usocket))

(in-package :socket-inspector)

(defparameter *rx-url* '("localhost" 4006)) 

(defparameter *tx-url* '(#(127 0 0 1) 4005))

(defun read-all (stream)
  (let ((output (make-array 0 :adjustable T
                               :fill-pointer 0)))
       (loop while (listen stream) 
            do (vector-push-extend (read-byte stream nil) output))
    output))

(defun print-relay (prefix rx-socket tx-socket)
  (let* ((rx-stream (socket-stream rx-socket))
         (tx-stream (socket-stream tx-socket))
         (buffer (read-all rx-stream)))
    ;; Return early should the buffer be empty
    (when (< 0 (length buffer))
      (terpri)
      (format t "~A~A:~A" prefix (length buffer) (map 'string #'code-char buffer))
      (write-sequence buffer tx-stream)
      (force-output tx-stream))))

(defvar swank (socket-connect (first *tx-url*) (second *tx-url*)
                              :element-type 'octet))
(princ "Swank connexion etabli")

(defvar clients (socket-listen (first *rx-url*) (second *rx-url*)
                               :element-type 'octet))
(princ "Searching for client   !")
(defvar client (socket-accept clients))

(princ "Client connexion etabli")    
    
(unwind-protect
  (loop (progn (print-relay "C 2 S " client swank)
               (print-relay "s à c " swank client)))
   (mapc socket-close (list clients client swank)))
 