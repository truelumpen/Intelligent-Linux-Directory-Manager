<img width="1760" height="568" alt="Diagram" src="https://github.com/user-attachments/assets/885559ae-b64b-4323-a366-bfc1a1195097" />
The work of Intelligent Linux Directory Manager in one diagram.

## Overview
Many users experience a cluttered ~/Downloads folder with hundreds of files collecting dust and taking up storage space. Our solution is to organize the ~/Downloads directory once and for all, automatically sorting incoming files into the right categories. The program is capable of categorizing files into directories based on their name, extension, and MIME type. It also tracks which files remain unused and gracefully moves them to the Trash. Don't let junk files spread across your storage—use Sorty!

## QuickStart
On Ubuntu, you will need to install an additional dependency if you don't have it already:
sudo apt install python3-venv

After the installation, proceed to the rest of the startup setup described below.

Starting the application:
sudo python main.py
or
sudo python3 main.py

## That's it!
To adjust the automatic deletion timer or customize the categories, use the config.py file. All daemon activities are logged to a .log file in the project folder.
