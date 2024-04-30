Python Application for enabling or disabling homeegramme to improve homee functionality by supporting holidays.

1. You must have a user with rights "Chef Homee" or "Homee"
2. Script is intended to be run on f.e. an raspberry pi with local connection to the homee cube
3. You must have two Homeegramme, one with the intended workflow for holidays and one for non holiday days. In my case the Homeegramme controls the time of the roller shutters. On vacation or holidays the time is later than on workdays
5. The script is checking if it is a holiday (default DE-NRW) and depending on the outcome one Homeegramm is been disabled and the other enabled.
