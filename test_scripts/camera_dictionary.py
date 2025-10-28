from picamera2 import Picamera2
pic = Picamera2()
infos = pic.global_camera_info()
print(infos)
# Then once configured:
pic.configure(pic.create_still_configuration(main={"size": (4656, 3496)}))
pic.start()
print("Controls:", pic.camera_controls.keys())
pic.stop()
