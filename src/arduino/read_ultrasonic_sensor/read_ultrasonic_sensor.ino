float distance = 0.0;
int trigger = 6;
int echo = 5;
int controlPin = 3;
unsigned long time;
unsigned long t0; 
bool measurementStarted = false;

float readUltrasonicDistance(int triggerPin, int echoPin) {
  digitalWrite(triggerPin, LOW);
  delayMicroseconds(2);
  digitalWrite(triggerPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(triggerPin, LOW);
  return 0.01723 * pulseIn(echoPin, HIGH);
}

void setup() {
  pinMode(controlPin, OUTPUT);
  pinMode(trigger, OUTPUT);
  pinMode(echo, INPUT);
  digitalWrite(controlPin, HIGH);
  Serial.begin(9600);
  delay(2000);
  digitalWrite(controlPin, LOW);
}


void loop() {
  if (Serial.available() > 0) {
    char command = Serial.read();
    if (command == 's') {
      measurementStarted = true;
      t0 = millis();
    } else if (command == 'p') {
      measurementStarted = false;
    }
  }


  if (measurementStarted) {
    distance = readUltrasonicDistance(trigger, echo);
    time = millis() - t0;
    Serial.print(time);
    Serial.print(",");
    Serial.println(distance);
  }
}

